"""brig's public entry point (decision-0001): create a bwrap jail, run a command in it,
and destroy it, wiring `domain/operations.py` through `presentation/drivers/bwrap.py`.

The only module that names `brig.infra.processes`'s own functions, so it can bind them
into the port's default implementation; a caller wanting a fake passes its own
`processes` instead. TASK-0001.15 step 4: the same is now true of
`brig.infra.supervisor.link`'s -- this module binds its one shared `LiveSupervisors`
instance into `SupervisorPort`'s default implementation, the same way.
"""

import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from brig.domain import operations
from brig.domain.effects import ExitCodeUnknown, GroupState, Process
from brig.domain.jail_types import bwrap
from brig.domain.policy.env import DENY_ALL, EnvPolicy
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, FsPolicy
from brig.infra.processes import ProcessUnknown as _InfraProcessUnknown
from brig.infra.processes import SpawnedProcess
from brig.infra.processes import group_alive as _group_alive
from brig.infra.processes import reap as _infra_reap
from brig.infra.processes import reap_deadline as _infra_reap_deadline
from brig.infra.processes import reap_nowait as _reap_nowait
from brig.infra.processes import signal_group as _signal_group
from brig.infra.processes import spawn as _spawn
from brig.infra.supervisor import link
from brig.infra.supervisor import program as _supervisor_program
from brig.presentation.drivers.bwrap import run
from brig.presentation.errors import JailExitUnknown, JailTeardownFailed, JailWaitTimedOut
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


_DEFAULT_WAIT_TIMEOUT_S = 30.0
"""How long `run_jail` waits for a jail's process to exit when an embedder gives no
`timeout_s` of its own (TASK-0001.06): long enough for an ordinary jailed command,
short enough that a jailed process which never exits on its own does not hang the
embedder forever.
"""

_SUPERVISOR_PATH: tuple[str, ...] = (sys.executable, "-I", _supervisor_program.__file__)
"""Where this host's own supervisor file actually is -- an interim stand-in for
AC#1's assembled stdlib-only file (TASK-0001.15): runs `infra/supervisor/program.py`
directly, as a script, through this same interpreter. Reachable inside a bwrap jail
under the default policy (`domain/policy/paths.py`'s `WHOLE_HOST_READ_ONLY`, TASK-
0001.16) because that policy binds the whole host root, read-only -- this venv and
this repository included -- the same bind the walking skeleton already relied on for
`true` to be reachable. A jail created with a narrower `policy` of its own is this
path's responsibility to stay reachable under too -- `create_bwrap_jail`'s own
`policy` parameter does not relax that, it is the caller's own policy that has to
still cover wherever this interpreter and `program.py` actually live. `program.py`
imports only the stdlib (its own docstring), which already satisfies rule 17's
"stdlib only" for the one thing that matters here: nothing it does, once running,
reaches back into brig. What this stand-in does *not* yet satisfy is "assembled...
one file" (AC#1, still open) -- replace it with the real dropped artifact's path once
that build step exists, and drop this paragraph.

`-I` (isolated mode, TASK-0001.15/.17 adversarial review) runs this interpreter
ignoring `PYTHONPATH`/`PYTHONHOME` and without adding user site-packages, regardless
of what this process's own environment happens to carry -- belt and braces next to
`infra.supervisor.link._start` no longer handing the supervisor process
`EnvPolicy`-scrubbed environment at all (that module's own docstring explains why a
mapping an embedder scrubbed for the *confined command* is not safe to also hand
the process enforcing the confinement): `-I` closes the same hole a second,
independent way, for whatever this process's own environment might someday carry.
It does nothing for `LD_PRELOAD`, which the dynamic linker consults before the
interpreter ever starts -- the env split is what closes that half. `program.py`
imports only the stdlib, so running it under `-I` changes nothing it does.
"""

_SUPERVISOR_ARGV: tuple[str, ...] = bwrap.compile_supervisor_launch(
    _SUPERVISOR_PATH, WHOLE_HOST_READ_ONLY
)
"""`_SUPERVISOR_PATH`, wrapped in bwrap's own namespace-isolation flags and the
default policy's binds (`domain/jail_types/bwrap.py`'s `compile_supervisor_launch`,
TASK-0001.16) -- the argv that starts the supervisor as a bwrap jail's own PID 1
under `WHOLE_HOST_READ_ONLY`, the policy every jail gets unless `create_bwrap_jail`
is given a different one. Computed once, here, for exactly that one policy; a jail
created with a different `policy` gets its own launch line instead, built fresh by
`_supervisors_for` below rather than varying this constant.
"""


@dataclass(frozen=True)
class _RealProcesses:
    """`brig.infra.processes`'s own functions, as the `ProcessPort` an embedder gets by
    default: data (six functions), nothing more, matching the port's shape exactly --
    `reap` and `reap_deadline` through this module's own thin adapters above, which
    translate infra's `ProcessUnknown` into the port's (`ports.py`'s own docstring).
    """

    spawn: Callable[[tuple[str, ...], tuple[int, ...]], SpawnedProcess] = _spawn
    reap: Callable[[int], int | ProcessUnknown] = _reap
    reap_deadline: Callable[[int, float], int | None | ProcessUnknown] = _reap_deadline
    signal_group: Callable[[int, signal.Signals], None] = _signal_group
    reap_nowait: Callable[[int], int | None] = _reap_nowait
    group_alive: Callable[[int], bool] = _group_alive


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

    A function, not a one-off inline adapter, because TASK-0001.16 needs it twice:
    once for the module's one shared `LiveSupervisors` instance below
    (`_live_supervisors`/`_supervisors`), and once more, per call, in
    `_supervisors_for`, for a jail whose own `policy` means a dedicated instance.
    """

    def await_done(pid: int, deadline: float) -> int | None | SupervisorDoneUnknown:
        outcome = live.await_done(pid, deadline)
        return (
            SupervisorDoneUnknown() if isinstance(outcome, link.SupervisorDoneUnknown) else outcome
        )

    return _RealSupervisors(start=live.start, await_done=await_done, close=live.close)


_live_supervisors = link.LiveSupervisors(_SUPERVISOR_ARGV)
"""The one shared `LiveSupervisors` instance a jail created under the default
policy (`WHOLE_HOST_READ_ONLY`) has its `create`/`start`/`destroy` driver calls
wired to -- it has to be the same instance across all three, since it is what
remembers which open `Supervisor` a `Process`'s pid still names between them
(`infra.supervisor.link.LiveSupervisors`'s own docstring). TASK-0001.16: a jail
created with a different `policy` gets its own dedicated instance from
`_supervisors_for` instead, since its own launch line for the supervisor's file
differs from this one's.
"""

_supervisors: SupervisorPort = _real_supervisor_port(_live_supervisors)
"""The real `SupervisorPort` every bwrap jail gets by default, when its own
`create_bwrap_jail` call names no `policy`/`supervisors` of its own.
"""


def _supervisors_for(policy: FsPolicy) -> SupervisorPort:
    """The `SupervisorPort` `create_bwrap_jail` uses for `policy`, when its own
    caller names no explicit `supervisors` port of its own (TASK-0001.16): the
    module's one shared instance (`_supervisors`) for `WHOLE_HOST_READ_ONLY`, the
    same instance every jail got before this parameter existed, or a dedicated
    `LiveSupervisors` -- built fresh here, cheap, since it does no I/O of its own
    until `start` is actually called -- for any other policy, since its own
    launch line for the supervisor's file depends on exactly which paths that
    policy names. A jail's own `LiveSupervisors` has to be its own instance
    either way once two jails' own policies differ (`link.LiveSupervisors`'s own
    docstring: whichever instance opened a jail's events pipe is the only one
    that can still read or close it) -- `Jail.supervisors` is what carries this
    one back to `run_jail`/`destroy_jail` for the same jail later.
    """
    if policy == WHOLE_HOST_READ_ONLY:
        return _supervisors
    supervisor_argv = bwrap.compile_supervisor_launch(_SUPERVISOR_PATH, policy)
    return _real_supervisor_port(link.LiveSupervisors(supervisor_argv))


@dataclass(frozen=True)
class Jail:
    """A bwrap jail an embedder created.

    `process` is the supervisor's own identity (decision-0002). `supervisors` is
    the one `SupervisorPort` this jail's own supervisor was started through --
    `run_jail`/`destroy_jail` default to it, rather than the module's own shared
    instance, because TASK-0001.16's `policy` parameter means two jails' own
    supervisor launch lines can differ, and whichever `LiveSupervisors` opened a
    jail's events pipe is the only one that can still read or close it
    (`infra.supervisor.link.LiveSupervisors`'s own invariant). Defaults to the
    module's own shared instance (`_supervisors`) so a `Jail` built directly, for
    a gateway test that never calls `create_bwrap_jail` at all
    (`tests/e2e/test_processes_gateway.py`), keeps working exactly as before.
    """

    process: Process
    supervisors: SupervisorPort = _supervisors


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

    `supervisors`, left unset, is resolved from `policy` (`_supervisors_for`); an
    explicit `supervisors` (a fake, in a test) is used as given instead, and
    `policy` then plays no part, the same way a fake stands in for the whole
    world regardless of what domain state asked for it.

    `presentation/drivers/bwrap.py`'s `run` raises `JailSpawnFailed` should the
    supervisor's own start fail; nothing in this function's own body raises, so it is
    not in this docstring.
    """
    resolved_supervisors = supervisors if supervisors is not None else _supervisors_for(policy)
    plan = bwrap.compile_run(command, env=env)
    process = run(operations.create(plan, env_policy), processes, resolved_supervisors)
    return Jail(process=process, supervisors=resolved_supervisors)


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
    processes: ProcessPort = _processes,
    supervisors: SupervisorPort | None = None,
) -> None:
    """Tear `jail` down, verified: no process of its group is left when this returns.

    Also releases whatever `supervisors` is still holding open for `jail`'s
    supervisor (`SupervisorPort.close`'s own docstring): a no-op if `run_jail`
    already did, by way of a terminal `await_done` outcome, so a jail destroyed
    without ever being run still gets that cleaned up here.

    `supervisors`, left unset, defaults to `jail.supervisors`, the same way
    `run_jail` resolves it (TASK-0001.16) -- the only port that still has `jail`'s
    own events pipe open to close, once its own `policy` differs from the default.

    Raises:
        JailTeardownFailed: the kill ladder's last verify still found the group alive.
    """
    resolved_supervisors = supervisors if supervisors is not None else jail.supervisors
    state = run(operations.destroy(jail.process), processes, resolved_supervisors)
    resolved_supervisors.close(jail.process.pid)
    if state is not GroupState.GONE:
        raise JailTeardownFailed(jail.process)
