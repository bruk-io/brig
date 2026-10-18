"""brig's public entry point (decision-0001): create a bwrap jail, run a command in it,
and destroy it, wiring `domain/operations.py` through `presentation/drivers/bwrap.py`.

The only module that names `brig.infra.processes`'s own functions, so it can bind them
into the port's default implementation; a caller wanting a fake passes its own
`processes` instead. TASK-0001.15 step 4: the same is now true of
`brig.infra.supervisor.link`'s -- this module binds a `LiveSupervisors` instance into
`SupervisorPort`'s default implementation, the same way. TASK-0001.21: that instance
is no longer shared across every jail a process creates -- `_supervisors_for` builds
a fresh one, with its own freshly-written supervisor script, per `create_bwrap_jail`
call, so `destroy_jail` can delete exactly one jail's own file without breaking any
other jail still running.
"""

import functools
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from brig.domain import operations
from brig.domain.effects import ExitCodeUnknown, GroupState, Process
from brig.domain.jail_types import bwrap
from brig.domain.policy.env import DENY_ALL, EnvPolicy
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, FsPolicy
from brig.infra import state_dir as _state_dir_mod
from brig.infra.processes import ProcessUnknown as _InfraProcessUnknown
from brig.infra.processes import SpawnedProcess
from brig.infra.processes import group_alive as _group_alive
from brig.infra.processes import group_alive_deadline as _group_alive_deadline
from brig.infra.processes import peek as _infra_peek
from brig.infra.processes import reap as _infra_reap
from brig.infra.processes import reap_deadline as _infra_reap_deadline
from brig.infra.processes import release as _release
from brig.infra.processes import signal_group as _signal_group
from brig.infra.processes import spawn as _spawn
from brig.infra.supervisor import assemble, link
from brig.presentation.drivers.bwrap import run
from brig.presentation.errors import (
    JailExitUnknown,
    JailTeardownFailed,
    JailWaitTimedOut,
    StateDirectoryInvalid,
    StateDirectoryUnreachable,
)
from brig.presentation.ports import (
    ProcessPort,
    ProcessUnknown,
    SupervisorDoneUnknown,
    SupervisorPort,
)


def _reap(pid: int) -> int | ProcessUnknown:
    """Adapt infra's `reap` to `ProcessPort`'s contract: translate infra's own
    `ProcessUnknown` sentinel into this port's, the one place the real wiring knows
    both (rule 13: no infra type crosses this port).
    """
    result = _infra_reap(pid)
    return ProcessUnknown() if isinstance(result, _InfraProcessUnknown) else result


def _reap_deadline(pid: int, deadline: float) -> int | None | ProcessUnknown:
    """Adapt infra's `reap_deadline` to `ProcessPort`'s contract, the same way `_reap`
    adapts `reap`.
    """
    result = _infra_reap_deadline(pid, deadline)
    return ProcessUnknown() if isinstance(result, _InfraProcessUnknown) else result


def _peek(pid: int) -> int | None | ProcessUnknown:
    """Adapt infra's `peek` to `ProcessPort`'s contract, the same way `_reap` adapts
    `reap` (decision-0003).
    """
    result = _infra_peek(pid)
    return ProcessUnknown() if isinstance(result, _InfraProcessUnknown) else result


_DEFAULT_WAIT_TIMEOUT_S = 30.0
"""How long `run_jail` waits for a jail's process to exit when an embedder gives no
`timeout_s` of its own (TASK-0001.06): long enough for an ordinary jailed command,
short enough that a jailed process which never exits on its own does not hang the
embedder forever.
"""

_DEFAULT_KILL_GRACE_S = 1.0
"""How long `destroy_jail` lets the kill ladder's post-KILL rung poll group-liveness
before giving up, when an embedder gives no `kill_grace_s` of its own (TASK-0001.07):
long enough that the kernel has finished processing `SignalKind.KILL` on an ordinary
multi-process group well before this passes, short enough that a group the kill
ladder genuinely cannot bring down does not hang `destroy_jail` for long before it
raises `JailTeardownFailed`.
"""


@functools.cache
def _resolved_state_dir() -> str:
    """Brig's own runtime-state directory (`infra/state_dir.py`, TASK-0006):
    resolved from `BRIG_HOME`/`~/.brig` and created if it does not exist yet,
    once per process and cached for the rest of this process's life -- unlike
    `_supervisor_path` below (TASK-0001.21: every jail needs its own fresh
    file, so that one is no longer cached), this directory itself is the same
    for every jail a process creates, so resolving and creating it once is
    enough. Real I/O (a `mkdir`, here) that must never run at import time.

    A plain string, not a `Path`: this is what crosses into domain
    (`compile_supervisor_launch`'s own `state_dir` parameter, rule 2 -- domain
    does no I/O to locate or create anything itself).

    `BRIG_HOME` is brig's own host-side operational setting, never routed
    through `EnvPolicy` scrubbing -- that governs what the *jailed command*
    sees in `env` (`domain/policy/env.py`'s own docstring), never brig's own
    configuration for where it writes its own files (`infra/state_dir.py`'s
    own docstring says the same).

    Raises:
        StateDirectoryInvalid: `BRIG_HOME` names a value `infra.state_dir.resolve`
            refuses (not an absolute path) -- translated from infra's own
            `ValueError` here, this module's own job under the driver-exception-
            boundary rule: the one place an infra exception becomes one of
            `presentation/errors.py`'s own types, so an embedder never needs to
            handle `infra`'s.
    """
    try:
        resolved = _state_dir_mod.resolve()
    except ValueError as exc:
        raise StateDirectoryInvalid(str(exc)) from exc
    return str(_state_dir_mod.ensure(resolved))


def _check_state_dir_reachable(policy: FsPolicy, state_dir: str) -> None:
    """Refuse, before bwrap is ever invoked, a `policy` that would leave `state_dir`
    unreachable inside the jail (TASK-0001.22): a read-only ancestor bind of
    `state_dir` whose own source does not already contain `state_dir`'s own leaf.
    `domain/jail_types/bwrap.py`'s `compile_supervisor_launch`'s unconditional bind
    still runs after `policy`'s own binds, so it is never shadowed at `state_dir`'s
    own exact path -- but bwrap creates a bind's missing mountpoint directories in
    the new root before applying that bind's own mount, in argv order, and a
    read-only ancestor bind whose source lacks the leaf means that creation fails
    with `EROFS`: measured against real bwrap as `bwrap: Can't mkdir <state_dir>:
    Read-only file system`, then `JailExitUnknown` (and `JailTeardownFailed` on the
    following `destroy_jail`). This function turns that into one clear, dedicated
    refusal instead, before bwrap is ever invoked at all.

    `bwrap.covering_ancestor_bind` (domain, pure) finds which of `policy`'s own
    binds, if any, actually governs `state_dir`'s own parent at that moment; this
    function does the one host filesystem existence check that decides whether it
    blocks `state_dir` -- I/O, which is why domain itself cannot do it (rule 2).

    A `None` or `writable` governing bind is always safe (measured against real
    bwrap: a writable ancestor works regardless of whether its own source contains
    the leaf, and no ancestor at all leaves bwrap's own new root -- a writable
    tmpfs by default -- free to create `state_dir` itself).

    Raises:
        StateDirectoryUnreachable: `policy` names a read-only ancestor bind of
            `state_dir` whose own source does not contain `state_dir`'s leaf.
    """
    ancestor = bwrap.covering_ancestor_bind(policy, state_dir)
    if ancestor is None or ancestor.writable:
        return
    suffix = state_dir[len(ancestor.jail_path.rstrip("/")) :]
    host_equivalent = ancestor.host_path.rstrip("/") + suffix
    if not Path(host_equivalent).is_dir():
        raise StateDirectoryUnreachable(state_dir, ancestor)


def _supervisor_path() -> tuple[str, ...]:
    """Where this host's own assembled supervisor file actually is: rule 17's
    one file (`infra.supervisor.assemble.assembled_source()` -- `wire.py` +
    `program.py`, stdlib only, refusing to run under an interpreter older
    than 3.15), written fresh to a new file inside brig's own state directory
    (`_resolved_state_dir`, TASK-0006) on every call.

    TASK-0001.21: no longer `functools.cache`d -- every jail needs its own
    file, so that `destroy_jail` can delete exactly the one file it no longer
    needs without also deleting a still-live jail's own (`_supervisors_for`'s
    own docstring has the reasoning). Never called at module scope: writing a
    file is real I/O, and `pyproject.toml`'s own `[tool.pypeeker.import-time-
    side-effects]` allow-list has no entry for this module, so doing this
    eagerly at import time would trip that rule, not just style. Called
    exactly once per `create_bwrap_jail` call that needs it (`_supervisors_for`,
    the one caller) -- a second call in the same jail's creation would write a
    second, decoy file and leak the first one forever once `destroy_jail`
    deletes the wrong path instead.

    Reachable inside a bwrap jail under most of the caller's own `policy`
    shapes (TASK-0006): `compile_supervisor_launch` binds `_resolved_state_dir()`
    unconditionally, so wherever `tempfile.NamedTemporaryFile`'s own
    collision-safe random suffix actually placed this file stays reachable
    even under a policy that excludes everything else this file used to
    depend on (`/tmp`, before this task; the whole host root, under
    `WHOLE_HOST_READ_ONLY`, incidentally covered it too). A jail created with
    a narrower `policy` of its own no longer has to also happen to cover this
    path -- that was exactly TASK-0006's bug.

    Not reachable under every policy, though: measured against real bwrap
    (adversarial review of TASK-0006/0009), a policy naming a *read-only*
    ancestor bind of this state directory, sourced from somewhere that does
    not already contain the directory's own leaf, still breaks the jail
    (`bwrap: Can't mkdir <state_dir>: Read-only file system` ->
    `JailExitUnknown`) -- `domain/jail_types/bwrap.py`'s own module docstring
    has the full, measured scope of what "unconditional" actually covers here.
    TASK-0001.22: rather than lift that limit (two candidate fixes were
    measured against real bwrap and both killed -- that module's own
    docstring has the measurements), `_supervisors_for`'s own
    `_check_state_dir_reachable` refuses a policy of that exact shape loudly,
    with `StateDirectoryUnreachable`, before this function is ever reached for
    that jail at all.

    `-I` (isolated mode, TASK-0001.15/.17 adversarial review) runs this
    interpreter ignoring `PYTHONPATH`/`PYTHONHOME` and without adding user
    site-packages, regardless of what this process's own environment happens
    to carry -- belt and braces next to `infra.supervisor.link._start` no
    longer handing the supervisor process `EnvPolicy`-scrubbed environment at
    all (that module's own docstring explains why a mapping an embedder
    scrubbed for the *confined command* is not safe to also hand the process
    enforcing the confinement): `-I` closes the same hole a second,
    independent way, for whatever this process's own environment might
    someday carry. It does nothing for `LD_PRELOAD`, which the dynamic linker
    consults before the interpreter ever starts -- the env split is what
    closes that half. The assembled file imports only the stdlib (rule 17),
    so running it under `-I` changes nothing it does.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        prefix="brig-supervisor-",
        delete=False,
        dir=_resolved_state_dir(),
    ) as handle:
        handle.write(assemble.assembled_source())
    return (sys.executable, "-I", handle.name)


@dataclass(frozen=True)
class _RealProcesses:
    """`brig.infra.processes`'s own functions, as the `ProcessPort` an embedder gets by
    default: data (seven functions), nothing more, matching the port's shape exactly --
    `reap`, `reap_deadline` and `peek` through this module's own thin adapters above,
    which translate infra's `ProcessUnknown` into the port's (`ports.py`'s own
    docstring). `release` and `group_alive`/`group_alive_deadline` need no adapter:
    neither crosses an infra-specific type (decision-0003).
    """

    spawn: Callable[[tuple[str, ...], tuple[int, ...]], SpawnedProcess] = _spawn
    reap: Callable[[int], int | ProcessUnknown] = _reap
    reap_deadline: Callable[[int, float], int | None | ProcessUnknown] = _reap_deadline
    signal_group: Callable[[int, signal.Signals], None] = _signal_group
    peek: Callable[[int], int | None | ProcessUnknown] = _peek
    release: Callable[[int], None] = _release
    group_alive: Callable[[int, frozenset[int]], bool] = _group_alive
    group_alive_deadline: Callable[[int, int, float], bool] = _group_alive_deadline


_processes: ProcessPort = _RealProcesses()


@dataclass(frozen=True)
class _RealSupervisors:
    """A `LiveSupervisors` instance's own methods, as the `SupervisorPort` an
    embedder gets by default -- `await_done` through `_real_supervisor_port`'s
    thin adapter, which translates infra's `SupervisorDoneUnknown` into the
    port's, mirroring `_RealProcesses`'s own `reap`/`reap_deadline` adapters.
    """

    start: Callable[[tuple[str, ...], tuple[tuple[str, str], ...]], link.Supervisor]
    await_done: Callable[[int, float], int | None | SupervisorDoneUnknown]
    close: Callable[[int], None]


def _real_supervisor_port(live: link.LiveSupervisors) -> SupervisorPort:
    """Wrap `live` as a `SupervisorPort`: translate infra's own
    `SupervisorDoneUnknown` into this port's, the one place the real wiring knows
    both -- the same move `_reap`/`_reap_deadline` make above for `ProcessPort`
    (rule 13: no infra type crosses a port).

    A function, not a one-off inline adapter, because `_supervisors_for` calls it
    once per `create_bwrap_jail` call (TASK-0001.21: every jail gets its own fresh
    `LiveSupervisors` now, never a module-level shared instance).
    """

    def await_done(pid: int, deadline: float) -> int | None | SupervisorDoneUnknown:
        outcome = live.await_done(pid, deadline)
        return (
            SupervisorDoneUnknown() if isinstance(outcome, link.SupervisorDoneUnknown) else outcome
        )

    return _RealSupervisors(start=live.start, await_done=await_done, close=live.close)


def _supervisors_for(policy: FsPolicy) -> tuple[SupervisorPort, Path]:
    """The `SupervisorPort` `create_bwrap_jail` uses for `policy`, when its own
    caller names no explicit `supervisors` port of its own, and the exact path of
    the fresh supervisor script file written for it, so the jail that gets this
    port back can later delete that one file and no other (TASK-0001.21).

    A fresh `LiveSupervisors`, every call -- never a module-level shared instance,
    regardless of `policy`: each jail's own instance is cheap to build (it does no
    I/O of its own until `start` is actually called) and has to be its own
    instance anyway once two jails' own policies differ (`link.LiveSupervisors`'s
    own docstring: whichever instance opened a jail's events pipe is the only one
    that can still read or close it) -- `Jail.supervisors` is what carries this one
    back to `run_jail`/`destroy_jail` for the same jail later.

    `_supervisor_path()` is called exactly once here, not twice: calling it again
    would write a second, decoy file and leak the one actually wired into
    `supervisor_argv` forever, since `destroy_jail` only ever deletes the path this
    function hands back, never searches the state directory for anything else.

    `_check_state_dir_reachable` (TASK-0001.22) runs before that write, raising
    `StateDirectoryUnreachable` should `policy` name a read-only ancestor bind of
    brig's own state directory whose source does not contain its leaf
    (`_check_state_dir_reachable`'s own docstring) -- `WHOLE_HOST_READ_ONLY`'s own
    single read-only bind at `/` is itself such an ancestor bind, though it never
    actually fails this check in practice (`_resolved_state_dir()` already created
    the leaf before this runs, so `/`'s own source always contains it).
    """
    state_dir = _resolved_state_dir()
    _check_state_dir_reachable(policy, state_dir)
    supervisor_path = _supervisor_path()
    supervisor_argv = bwrap.compile_supervisor_launch(
        supervisor_path, state_dir=state_dir, policy=policy
    )
    return _real_supervisor_port(link.LiveSupervisors(supervisor_argv)), Path(supervisor_path[-1])


@dataclass(frozen=True)
class Jail:
    """A bwrap jail an embedder created.

    `process` is the supervisor's own identity (decision-0002). `supervisors` is
    the one `SupervisorPort` this jail's own supervisor was started through --
    `run_jail`/`destroy_jail` default to it, since TASK-0001.16's `policy`
    parameter means two jails' own supervisor launch lines can differ, and
    whichever `LiveSupervisors` opened a jail's events pipe is the only one that
    can still read or close it (`infra.supervisor.link.LiveSupervisors`'s own
    invariant). No default of its own any more (TASK-0001.21: there is no module-
    level shared instance left to fall back to) -- a `Jail` built directly, for a
    gateway test that never calls `create_bwrap_jail` at all
    (`tests/e2e/test_processes_gateway.py`), now has to name its own.

    `supervisor_script` is the path of the fresh supervisor script file
    `_supervisors_for` wrote for this jail, for `destroy_jail` to delete once its
    own teardown has run (TASK-0001.21; TASK-0012: whether or not that teardown
    found `GroupState.GONE` -- `destroy_jail`'s own docstring has the reasoning
    for why that is still safe) -- `None` for a `Jail` built with an explicit
    `supervisors` of its own (`create_bwrap_jail` never wrote a file for it in the
    first place) or built directly, outside `create_bwrap_jail`, the same as the
    gateway test above.
    """

    process: Process
    supervisors: SupervisorPort
    supervisor_script: Path | None = None


def create_bwrap_jail(
    command: tuple[str, ...],
    *,
    env: tuple[tuple[str, str], ...] = (),
    policy: FsPolicy = WHOLE_HOST_READ_ONLY,
    env_policy: EnvPolicy = DENY_ALL,
    processes: ProcessPort = _processes,
    supervisors: SupervisorPort | None = None,
) -> Jail:
    """Compile `command` into a bwrap jail and start its supervisor running it,
    seeing exactly the paths `policy` names (TASK-0001.16) and exactly the
    environment variables `env_policy` allows out of `env` (TASK-0001.17).

    `policy` defaults to `WHOLE_HOST_READ_ONLY` (`domain/policy/paths.py`), the
    same whole host root, read-only, every jail got before that parameter existed.
    `env` is the candidate environment (`Plan.env`'s own docstring: not yet
    scrubbed) a caller has to offer; left unset, it is empty, so `env_policy`
    defaults to `DENY_ALL` (`domain/policy/env.py`) and scrubs nothing out of
    nothing -- the same no-environment-at-all behaviour every jail got before
    either parameter existed, now reached by an explicit policy rather than a
    bare default with no policy behind it. `operations.create` is the one place
    `env_policy` is ever applied (`domain/operations.py`'s own docstring): by the
    time this function's own `run` performs the yielded `StartSupervisedCommand`,
    the effect's `env` is already scrubbed, and nothing downstream (this driver,
    `infra/supervisor/link.py`) ever reads `env` or `os.environ` again to get
    there.

    `supervisors`, left unset, is resolved from `policy` (`_supervisors_for`),
    which also writes this jail's own fresh supervisor script file and hands
    back its path, carried on the returned `Jail` as `supervisor_script` for
    `destroy_jail` to delete later (TASK-0001.21). An explicit `supervisors` (a
    fake, in a test) is used as given instead, and `policy` then plays no part,
    the same way a fake stands in for the whole world regardless of what domain
    state asked for it -- no file was written for it, so `supervisor_script` is
    `None` on the `Jail` this returns.

    `presentation/drivers/bwrap.py`'s `run` raises `JailSpawnFailed` should the
    supervisor's own start fail. Resolving brig's own state directory
    (`_resolved_state_dir`, above) raises `StateDirectoryInvalid` should
    `BRIG_HOME` name a value it cannot use. `_supervisors_for` raises
    `StateDirectoryUnreachable` should `policy` name a read-only ancestor bind
    of that state directory whose own source lacks its leaf (TASK-0001.22).
    Nothing else in this function's own body raises, so nothing else is in this
    docstring.

    TASK-0012: once `_supervisors_for` has written `supervisor_script`, no `Jail`
    exists yet to carry that path to a later `destroy_jail` call -- this is the
    only function that still holds it. Should `run` raise anything at all before
    returning (`JailSpawnFailed`, the one documented case, but this catches
    unconditionally rather than naming it, so a future failure added to that call
    is never a second leak to rediscover), the just-written file is deleted here
    before the exception propagates unchanged: a side effect alongside the raise,
    never a replacement for it.
    """
    if supervisors is not None:
        resolved_supervisors: SupervisorPort = supervisors
        supervisor_script: Path | None = None
    else:
        resolved_supervisors, supervisor_script = _supervisors_for(policy)
    plan = bwrap.compile_run(command, env=env)
    try:
        process = run(operations.create(plan, env_policy), processes, resolved_supervisors)
    except BaseException:
        if supervisor_script is not None:
            supervisor_script.unlink(missing_ok=True)
        raise
    return Jail(
        process=process, supervisors=resolved_supervisors, supervisor_script=supervisor_script
    )


def run_jail(
    jail: Jail,
    *,
    timeout_s: float = _DEFAULT_WAIT_TIMEOUT_S,
    processes: ProcessPort = _processes,
    supervisors: SupervisorPort | None = None,
) -> int:
    """Wait for `jail`'s supervisor to report its supervised command's exit code.

    Gives up after `timeout_s` seconds (`_DEFAULT_WAIT_TIMEOUT_S` if not given) rather
    than blocking forever on a jailed process that never exits on its own.

    `supervisors`, left unset, defaults to `jail.supervisors` -- whichever port
    `create_bwrap_jail` actually started this jail's supervisor through
    (TASK-0001.16), rather than the module's own shared instance, since a jail
    created with a non-default `policy` has its own. An explicit `supervisors` (a
    fake, in a test) is used as given instead.

    Raises:
        JailWaitTimedOut: the process did not exit within `timeout_s`. Unlike
            `JailSpawnFailed` (nothing was created) or `JailTeardownFailed` (teardown
            already ran), this leaves `jail`'s process still running and unreaped --
            `destroy_jail(jail)` is still required to tear it down. Calling
            `run_jail` again on the same `jail`, with a fresh `timeout_s`, is also a
            valid way to keep waiting: the supervisor's own events pipe is left open
            for exactly that.
        JailExitUnknown: the supervisor's report for this process was no longer
            recoverable by the time `run_jail` waited on it. Unlike
            `JailWaitTimedOut`, retrying the wait can never succeed.
    """
    resolved_supervisors = supervisors if supervisors is not None else jail.supervisors
    deadline = time.monotonic() + timeout_s
    exit_code = run(
        operations.start(jail.process, deadline=deadline), processes, resolved_supervisors
    )
    if isinstance(exit_code, ExitCodeUnknown):
        raise JailExitUnknown(jail.process)
    if exit_code is None:
        raise JailWaitTimedOut(jail.process)
    return exit_code


def destroy_jail(
    jail: Jail,
    *,
    kill_grace_s: float = _DEFAULT_KILL_GRACE_S,
    processes: ProcessPort = _processes,
    supervisors: SupervisorPort | None = None,
) -> None:
    """Tear `jail` down, verified: no process of its group is left when this returns.

    `kill_grace_s` (`_DEFAULT_KILL_GRACE_S` if not given) bounds the kill ladder's
    post-KILL rung (TASK-0001.07): once `SignalKind.KILL` is sent, that rung polls
    group-liveness for up to this long before giving up, rather than deciding the
    instant after KILL -- the kernel finishing what KILL started is not
    instantaneous, and a multi-process group's leader exiting no longer provides a
    blocking barrier for the rest to finish behind (`domain/teardown.py`'s own
    module docstring, decision-0003).

    Also releases whatever `supervisors` is still holding open for `jail`'s
    supervisor (`SupervisorPort.close`'s own docstring): a no-op if `run_jail`
    already did, by way of a terminal `await_done` outcome, so a jail destroyed
    without ever being run still gets that cleaned up here.

    `supervisors`, left unset, defaults to `jail.supervisors`, the same way
    `run_jail` resolves it (TASK-0001.16) -- the only port that still has `jail`'s
    own events pipe open to close, once its own `policy` differs from the default.

    Deletes `jail.supervisor_script`, if it names one (TASK-0001.21: `None` for a
    `Jail` built with its own explicit `supervisors`, or built directly outside
    `create_bwrap_jail`, neither of which had a file written for them) -- once the
    kill ladder's own verify has run, whether or not it found `GroupState.GONE`
    (TASK-0012). The file only ever needs to not be deleted *before* it was exec'd,
    never while a process is still running from it, and by the time teardown's own
    verify has run at all, any exec that was ever going to happen already happened:
    the supervisor either already read and exec'd the script, or it never will,
    since nothing past this point gives it another chance to start reading it for
    the first time. A `JailTeardownFailed` (the group still alive after the kill
    ladder) means a process from that group may still be running -- never that the
    *script file itself* might still be read for the first time, which is the only
    thing deleting it early would risk. `missing_ok=True` makes a repeated
    `destroy_jail` call on an already-torn-down `jail` safe; any other `OSError`
    the deletion itself raises (a permissions change, a read-only state directory)
    is swallowed rather than escaping a teardown that has already run its own
    verify -- the same way `Supervisor.close` swallows a close failure during
    teardown (`infra/supervisor/link.py`'s own docstring).

    Raises:
        JailTeardownFailed: the kill ladder's last verify still found the group alive.
    """
    resolved_supervisors = supervisors if supervisors is not None else jail.supervisors
    deadline = time.monotonic() + kill_grace_s
    state = run(
        operations.destroy(jail.process, deadline=deadline), processes, resolved_supervisors
    )
    resolved_supervisors.close(jail.process.pid)
    if jail.supervisor_script is not None:
        try:
            jail.supervisor_script.unlink(missing_ok=True)
        except OSError:
            pass
    if state is not GroupState.GONE:
        raise JailTeardownFailed(jail.process)
