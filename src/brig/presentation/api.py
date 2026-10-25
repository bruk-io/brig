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

TASK-0001.25: `reserve_channels` is the one public call made *before* a jail exists --
it hands back each declared channel's reservation, so the embedder can write each
endpoint into the command's argv itself before `create_bwrap_jail` starts anything.
"""

import functools
import os
import secrets
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from brig.domain import channels as _channels
from brig.domain import operations
from brig.domain.channels import (
    Channel,
    ChannelDirectory,
    Reservation,
    Reservations,
)
from brig.domain.channels import ChannelRefused as _ChannelNameRefused
from brig.domain.effects import ExitCodeUnknown, GroupState, Process
from brig.domain.jail_types import bwrap
from brig.domain.policy.env import DENY_ALL, EnvPolicy
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, Bind, FsPolicy
from brig.infra import sockets as _sockets
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
    ChannelDirectoryUnreachable,
    ChannelNameRefused,
    ChannelNamespaceNotFound,
    JailExitUnknown,
    JailTeardownFailed,
    JailWaitTimedOut,
    StateDirectoryInvalid,
    StateDirectoryUnreachable,
)
from brig.presentation.ports import (
    ChannelDirectoryPort,
    ChannelNotReady,
    ChannelReadinessPort,
    ChannelReadinessRefusal,
    ChannelReady,
    ChannelRefused,
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

_DEFAULT_CHANNEL_READY_TIMEOUT_S = 30.0
"""How long `await_channel_ready` keeps polling when an embedder gives no
`timeout_s` of its own (TASK-0001.27).

The same number as `_DEFAULT_WAIT_TIMEOUT_S`, for the same reason and as an
independent constant rather than a shared one: both bound "wait for the thing the
jail runs to get going", one on the process finishing and one on its listener
coming up, and a change to either should be a decision about that one.
"""

_CHANNEL_READY_POLL_INTERVAL_S = 0.05
"""How long `await_channel_ready` waits between readiness attempts.

A whole verified connect is a `connect` syscall plus several `/proc` reads, so this
is deliberately not the ~10ms range `infra/processes.py` polls a single syscall at
(`_POLL_INTERVAL_S` there) nor `infra/sockets.py`'s own scan interval -- at this
layer the cost per attempt is the reason the number exists.
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


def _check_channel_directory_reachable(policy: FsPolicy, state_dir: str, channel_dir: str) -> None:
    """Refuse, before anything starts or is created, a `policy` that would leave a
    jail's per-jail channel directory unreachable (TASK-0001.26): the same guard as
    `_check_state_dir_reachable`, generalised rather than copied -- it calls the
    same, unchanged `bwrap.covering_ancestor_bind` on a richer input.

    That input is `policy`'s binds plus the unconditional read-only bind of
    `state_dir` that `compile_supervisor_launch` appends after them (its argv order:
    policy binds, then the `state_dir` bind, then the channel bind), so the synthetic
    bind here is always the *last* ancestor of any path nested under `state_dir` and
    always wins over whatever `policy` names on its own, when `channel_dir` is
    nested under `state_dir` at all (a custom `ChannelDirectoryPort` need not put it
    there, `ports.py`'s own docstring).

    A winning ancestor is safe -- nothing is refused -- when it is writable (TASK-
    0001.22's own finding, unchanged by anything here), *or* when `channel_dir`'s
    own real host-side location genuinely sits inside `ancestor.host_path`'s own
    real directory tree: a `--bind`/`--ro-bind` mounts whatever that real directory
    *currently* holds, live, not a snapshot taken at argv-compile time, so brig
    creating the leaf there before bwrap runs (`create_bwrap_jail`) is enough,
    regardless of whether the ancestor is read-only. `ancestor.host_path == state_dir`
    (the synthetic bind above) is one instance of this -- the default allocator
    always places `channel_dir` under `state_dir` -- but it is not the only one:
    `WHOLE_HOST_READ_ONLY`'s own single `Bind(host_path="/", jail_path="/")` is a
    real, unmapped ancestor of *every* absolute path, `channel_dir` included,
    regardless of where a caller's own `ChannelDirectoryPort` puts it (measured as a
    real `ChannelDirectoryUnreachable` false refusal on real bwrap before this
    docstring's own correction: TASK-0001.27's own battery allocates its channel
    directory under pytest's `tmp_path`, not `state_dir`, and the earlier version of
    this function -- checking only for the exact `state_dir` self-bind -- refused it
    under the plain default policy, which is exactly the shape every other jail in
    this codebase already relies on to reach paths outside `state_dir` too).
    `ancestor.host_path` is not treated as a *remapped* ancestor's own real
    directory happening to already contain a coincidentally-matching path: that
    would need the filesystem check `_check_state_dir_reachable` makes, which this
    function still does not need, because a prefix match on `channel_dir` itself
    (not a derived "host equivalent" path) is already answering the right question
    here -- whether the leaf *will* appear through this exact ancestor once created,
    not whether some other path already does.

    The one case brig cannot repair is a channel directory under a read-only
    ancestor bind whose own host-side directory tree does *not* actually contain
    where `channel_dir` really lives -- a policy bind that remaps some other real
    location onto an ancestor of `channel_dir`'s jail-side path. This relies on
    `compile_supervisor_launch`'s argv order holding; a reordering there would
    silently break this guard rather than loudly.

    Raises:
        ChannelDirectoryUnreachable: the winning ancestor is read-only and
            `channel_dir`'s own real location does not sit inside its host-side
            directory tree.
    """
    augmented = FsPolicy(binds=(*policy.binds, Bind(host_path=state_dir, jail_path=state_dir)))
    ancestor = bwrap.covering_ancestor_bind(augmented, channel_dir)
    if ancestor is None or ancestor.writable:
        return
    if channel_dir.startswith(ancestor.host_path.rstrip("/") + "/"):
        return
    raise ChannelDirectoryUnreachable(channel_dir, ancestor)


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


def _supervisors_for(
    policy: FsPolicy, channels: Reservations | None
) -> tuple[SupervisorPort, Path]:
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

    `channels` (TASK-0001.25) reaches `compile_supervisor_launch` unchanged, which
    binds its channel directory writable when it declares any channel.
    `_check_channel_directory_reachable` (TASK-0001.26) runs right after the
    state-directory check, and only when `channels` declares one: it raises
    `ChannelDirectoryUnreachable` before the script write below, so nothing is
    left behind to clean up.
    """
    state_dir = _resolved_state_dir()
    _check_state_dir_reachable(policy, state_dir)
    if channels is not None and channels.reservations:
        _check_channel_directory_reachable(policy, state_dir, channels.directory.host_path)
    supervisor_path = _supervisor_path()
    supervisor_argv = bwrap.compile_supervisor_launch(
        supervisor_path, state_dir=state_dir, policy=policy, channels=channels
    )
    return _real_supervisor_port(link.LiveSupervisors(supervisor_argv)), Path(supervisor_path[-1])


def _allocate_channel_directory() -> str:
    """Name a fresh per-jail channel directory under brig's own state directory
    (`_resolved_state_dir`), never `/tmp` -- a random component per call, so no two
    jails share one. Creates nothing -- `_RealChannelDirectories.create` does, later,
    in `create_bwrap_jail` (TASK-0001.26). `_resolved_state_dir` raises `StateDirectoryInvalid`
    should `BRIG_HOME` name a value brig cannot use.
    """
    return f"{_resolved_state_dir()}/channels/{secrets.token_hex(8)}"


@dataclass(frozen=True)
class _RealChannelDirectories:
    """The `ChannelDirectoryPort` an embedder gets by default: data (one function),
    the same shape `_RealProcesses` gives `ProcessPort`.
    """

    allocate: Callable[[], str] = _allocate_channel_directory
    create: Callable[[str], None] = _sockets.create
    remove: Callable[[str], None] = _sockets.remove


_channel_directories: ChannelDirectoryPort = _RealChannelDirectories()


def _channel_ready(
    path: str, jail_namespace_fd: int
) -> ChannelReady | ChannelNotReady | ChannelRefused:
    """Adapt infra's `sockets.channel_ready` to `ChannelReadinessPort`'s contract:
    translate infra's own `ChannelRefusalReason` strings and its `ChannelReady`/
    `ChannelNotReady` sentinels into this port's values -- the one place the real
    wiring knows both (rule 13: no infra type crosses a port), the same move
    `_reap` makes above for `ProcessPort`.

    Classified by `isinstance`, one branch per infra sentinel, rather than by a
    `match` on `_sockets`'s own class patterns: pypeeker's resolver cannot follow a
    class reference reached through a module alias inside a pattern (measured --
    every `case _sockets.X()` read as a zero-origin symbol and tripped
    `over-exposed-module-symbol` on `X` itself, with a fix-it that would have made
    this module's own public names private). The isinstance form resolves, and says
    the same thing.

    Exhaustive over infra's values by construction: `channel_ready` returns exactly
    one of those three, and the `assert_never` keeps a fourth from being added
    silently.
    """
    outcome = _sockets.channel_ready(path, jail_namespace_fd)
    if isinstance(outcome, _sockets.ChannelReady):
        return ChannelReady()
    if isinstance(outcome, _sockets.ChannelNotReady):
        return ChannelNotReady()
    if isinstance(outcome, _sockets.ChannelRefused):
        return ChannelRefused(ChannelReadinessRefusal(outcome.reason))
    assert_never(outcome)


@dataclass(frozen=True)
class _RealChannelReadiness:
    """The `ChannelReadinessPort` an embedder gets by default: data (one function),
    the same shape `_RealChannelDirectories` gives `ChannelDirectoryPort`.
    """

    ready: Callable[[str, int], ChannelReady | ChannelNotReady | ChannelRefused] = _channel_ready


_channel_readiness: ChannelReadinessPort = _RealChannelReadiness()


def reserve_channels(
    channels: tuple[Channel, ...],
    *,
    directories: ChannelDirectoryPort = _channel_directories,
) -> Reservations:
    """Reserve each of `channels` for a jail not yet created (TASK-0001.25), and hand
    back every reservation before anything starts.

    The caller reads each `Reservation.endpoint`, writes it into the command's argv
    itself, then passes these same `Reservations` to `create_bwrap_jail`'s
    `channels` -- argv, never env (old SPEC decision-184/186), so nothing that
    scrubs the jailed command's environment can lose it. bwrap binds the channel
    directory at its own host path, so each endpoint equals its `bound_path`
    (`ChannelDirectory`'s own docstring).

    `directories` names the per-jail channel directory; left unset, a fresh path
    under brig's own state directory, whose resolution raises `StateDirectoryInvalid`
    should `BRIG_HOME` name a value brig cannot use (`_resolved_state_dir`).

    Raises:
        ChannelNameRefused: a channel's name would escape or repeat in the channel
            directory (`domain/channels.py`'s `reserve`).
    """
    host_path = directories.allocate()
    directory = ChannelDirectory(host_path=host_path, jail_path=host_path)
    match _channels.reserve(channels, directory):
        case Reservations() as reservations:
            return reservations
        case _ChannelNameRefused(name=name):
            raise ChannelNameRefused(name)
        case _ as unreachable:
            assert_never(unreachable)


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

    `channel_directory` is the per-jail channel directory `create_bwrap_jail`
    created for this jail (TASK-0001.26), for `destroy_jail` to remove -- `None`
    when the jail declares no channel, or for a `Jail` built directly. Set only
    once `directories.create` has actually returned, so a `Jail` that exists never
    names a directory its creation did not finish.

    `channel_namespace_fd` is an open fd on this jail's own PID namespace
    (TASK-0001.27), which `await_channel_ready` compares a channel peer against;
    `destroy_jail` closes it. `None` when the jail declares no channel: no
    namespace was ever looked up, and there is nothing to compare. The fd is the
    *namespace*, not a pid -- decision-0005 item 1 holds the nsfs inode open for
    the jail's whole lifetime so it cannot be recycled under a later check -- and
    it is deliberately not the bwrap process's own namespace, which is the host's
    (`infra/sockets.py`'s `jail_pid1_namespace` has the measurement).
    """

    process: Process
    supervisors: SupervisorPort
    supervisor_script: Path | None = None
    channel_directory: Path | None = None
    channel_namespace_fd: int | None = None


def create_bwrap_jail(
    command: tuple[str, ...],
    *,
    env: tuple[tuple[str, str], ...] = (),
    policy: FsPolicy = WHOLE_HOST_READ_ONLY,
    env_policy: EnvPolicy = DENY_ALL,
    channels: Reservations | None = None,
    processes: ProcessPort = _processes,
    supervisors: SupervisorPort | None = None,
    directories: ChannelDirectoryPort = _channel_directories,
    proc_root: str = "/proc",
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

    `channels` is what `reserve_channels` handed back for this jail (TASK-0001.25):
    its channel directory is bound into the jail, writable, when it declares any
    channel. It reaches the jailed command only through `command` -- the caller has
    already written each endpoint there -- and never through `env`, which this
    function neither reads nor extends with it (old SPEC decision-184/186). The
    directory itself is created here (TASK-0001.26), through `directories`, when
    `channels` declares any channel: private to the owning user, under brig's own
    state directory, before the jail starts (bwrap would otherwise fail to make
    its mountpoint beneath the read-only state-directory bind). It is carried on
    the returned `Jail` as `channel_directory` for `destroy_jail` to remove.

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
    of that state directory whose own source lacks its leaf (TASK-0001.22), and
    `ChannelDirectoryUnreachable` should it leave the channel directory
    unreachable (TASK-0001.26), while `_namespace_fd_for` (below) raises
    `ChannelNamespaceNotFound` for a channel-declaring jail whose in-jail PID 1
    never appears (TASK-0001.27). `directories.create`'s own `OSError` (a full or
    read-only disk) propagates as-is: it is a host filesystem failure with no
    typed counterpart in `presentation/errors.py` yet. Nothing else in this
    function's own body raises, so nothing else is in this docstring.

    TASK-0012: once `_supervisors_for` has written `supervisor_script`, no `Jail`
    exists yet to carry that path to a later `destroy_jail` call -- this is the
    only function that still holds it. Should `run` raise anything at all before
    returning (`JailSpawnFailed`, the one documented case, but this catches
    unconditionally rather than naming it, so a future failure added to that call
    is never a second leak to rediscover), the just-written file is deleted here
    before the exception propagates unchanged: a side effect alongside the raise,
    never a replacement for it.

    TASK-0001.26: `directories.create` runs inside that same `try`, not before it,
    because it can itself fail partway (`mkdir` succeeds, `chmod` does not) -- a
    directory created outside the `try` would leak exactly like the script did.
    The `except` therefore removes the channel directory too, swallowing `OSError`
    the same way `destroy_jail` does (and safe when `create` never finished:
    `remove` on a path `mkdir` already made still finds something to delete),
    before the original exception propagates. `Jail.channel_directory` is set only
    once `create` returned.

    TASK-0001.27: for a jail that declares a channel, the jail's own PID namespace
    is looked up here too, once the supervisor has actually started (`process.pid`
    -- the *outer* bwrap process -- is what the scan is rooted at), inside the same
    `try` and for the same leak reason as `directories.create`: a
    `ChannelNamespaceNotFound` must not leave the channel directory or the script
    behind either -- and should anything later in the same `try` raise, the
    namespace fd this call already opened is closed on the way out, so a failure
    here leaks neither a directory, nor a script, nor an fd.
    `infra.sockets.jail_pid1_namespace` is called directly rather than through a
    port (`ChannelReadinessPort`'s own docstring: nothing needs to fake "which pid
    is bwrap's child"). The resulting fd is carried as `Jail.channel_namespace_fd`.

    `proc_root` is `/proc` for every production caller, and is passed straight
    through to `_namespace_fd_for`: it exists so a test can plant a directory tree
    of its own rather than need a real bwrap jail underneath the scan, the same
    parameter `infra.processes.group_alive` already carries (TASK-0016).
    """
    if supervisors is not None:
        resolved_supervisors: SupervisorPort = supervisors
        supervisor_script: Path | None = None
    else:
        resolved_supervisors, supervisor_script = _supervisors_for(policy, channels)
    channel_directory = (
        Path(channels.directory.host_path)
        if channels is not None and channels.reservations
        else None
    )
    created: Path | None = None
    namespace_fd: int | None = None
    try:
        if channel_directory is not None:
            directories.create(str(channel_directory))
            created = channel_directory
        plan = bwrap.compile_run(command, env=env)
        process = run(operations.create(plan, env_policy), processes, resolved_supervisors)
        if channel_directory is not None:
            namespace_fd = _namespace_fd_for(process, proc_root)
    except BaseException:
        if supervisor_script is not None:
            supervisor_script.unlink(missing_ok=True)
        if created is not None:
            try:
                directories.remove(str(created))
            except OSError:
                pass
        if namespace_fd is not None:
            _close_namespace_fd(namespace_fd)
        raise
    return Jail(
        process=process,
        supervisors=resolved_supervisors,
        supervisor_script=supervisor_script,
        channel_directory=created,
        channel_namespace_fd=namespace_fd,
    )


def _namespace_fd_for(process: Process, proc_root: str = "/proc") -> int:
    """The open fd on the jail's own PID namespace, found under `process` -- the
    *outer* bwrap process `create_bwrap_jail` just started -- or
    `ChannelNamespaceNotFound` once `infra.sockets.JAIL_PID1_TIMEOUT_S` passes.

    `infra.sockets.jail_pid1_namespace` is called with a `time.monotonic()`
    deadline computed here, never with that module's own constant: infra takes a
    deadline rather than computing one, the same split `infra.processes.
    reap_deadline` already has (rule 2: the module that decides what "too long"
    means is presentation's, the one that waits is infra's).

    That deadline (and so the frozen duration it is built from) is what this
    function adds to `create_bwrap_jail`'s own documented failure set, alongside
    the `OSError` its `directories.create` call can already raise.

    Raises:
        ChannelNamespaceNotFound: nothing under `process.pid` looked like the jail's
            in-jail PID 1 before the deadline passed.

    `proc_root` is `/proc` for every production caller; it exists so a test can plant
    a directory tree of its own instead of a real bwrap jail, the same parameter
    `infra.processes.group_alive` already carries for the same reason (TASK-0016).
    """
    outcome = _sockets.jail_pid1_namespace(
        process.pid, time.monotonic() + _sockets.JAIL_PID1_TIMEOUT_S, proc_root
    )
    if isinstance(outcome, _sockets.JailPid1NotFound):
        raise ChannelNamespaceNotFound(process.pid)
    return outcome


def _close_namespace_fd(fd: int) -> None:
    """Close `fd`, swallowing `OSError`, the same way every other teardown cleanup
    in this module does: an already-closed fd is fine, and nothing that runs after
    teardown's own verify should raise over it.
    """
    try:
        os.close(fd)
    except OSError:
        pass


def await_channel_ready(
    jail: Jail,
    reservation: Reservation,
    *,
    timeout_s: float = _DEFAULT_CHANNEL_READY_TIMEOUT_S,
    readiness: ChannelReadinessPort = _channel_readiness,
) -> ChannelReady | ChannelNotReady | ChannelRefused:
    """Poll until `reservation`'s channel in `jail` reads ready or refused, or
    `timeout_s` passes -- and report which (decision-0002 item 2, decision-0005).

    Each iteration asks `readiness.ready(reservation.bound_path,
    jail.channel_namespace_fd)`: a *verified* connect, never a path check, so what
    comes back is a statement about a peer that actually answered rather than about
    a file that happens to exist (TASK-0001.24's probe measured what the path-based
    alternative accepts -- a real socket inode with somebody else listening on it).

    Two of the three outcomes are terminal, and the third is not. `ChannelReady` is
    the answer being waited for; `ChannelRefused` is a security answer about *this*
    connection and is returned at once, never retried -- decision-0005 item 1:
    readiness is a property of that one connection, so a consumer that reconnects
    must verify again, which is the caller's decision to make and not this loop's.
    `ChannelNotReady` is the only transient one; once `timeout_s` passes with
    nothing else seen, the last one is what this returns.

    `timeout_s` defaults to `_DEFAULT_CHANNEL_READY_TIMEOUT_S`; the poll interval
    balances a peer that is about to be ready against syscall cost. The deadline is
    enforced between attempts, so one attempt that blocks does so for as long as the
    connect itself takes -- a Unix socket connect is not something this layer can
    bound from outside.

    `jail.channel_namespace_fd` is `None` for a jail that declared no channel, and
    that is a caller precondition violation rather than an outcome: there is no
    namespace to verify against, and the reservation being asked about cannot have
    come from that jail's `reserve_channels` call. Checked explicitly, rather than
    left to whatever `readiness.ready` would do with a `None` fd (a real
    `ChannelReadinessPort` would format it into a path string and read a confusing
    `FileNotFoundError` back) -- mypy strict would refuse this call unchecked too,
    since the port's own contract takes `int`, never `int | None`.

    Raises:
        ValueError: `jail.channel_namespace_fd` is `None`.
    """
    if jail.channel_namespace_fd is None:
        raise ValueError(
            "jail declared no channel: await_channel_ready has no namespace to "
            "verify a peer against"
        )
    deadline = time.monotonic() + timeout_s
    while True:
        outcome = readiness.ready(reservation.bound_path, jail.channel_namespace_fd)
        if not isinstance(outcome, ChannelNotReady):
            return outcome
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return outcome
        time.sleep(min(_CHANNEL_READY_POLL_INTERVAL_S, remaining))


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
    directories: ChannelDirectoryPort = _channel_directories,
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

    Removes `jail.channel_directory` the same way, if it names one (TASK-0001.26):
    after the script, whether or not teardown found `GroupState.GONE`, swallowing
    `OSError` for the same reasons (an already-gone directory, or a repeated
    `destroy_jail`, is fine; nothing escapes a teardown that already ran its own
    verify). `channel_directory` rides on `Jail` regardless of whether `run_jail`
    ever ran, so a jail destroyed before it ever ran is cleaned up by this one call
    site, and the sockets the jailed command created inside are removed with it.

    Closes `jail.channel_namespace_fd` too, if it names one (TASK-0001.27): the fd
    `create_bwrap_jail` opened on the jail's own PID namespace, held open only so a
    readiness check had something stable to compare against, and needed by nothing
    once this jail is gone (`_close_namespace_fd` swallows `OSError`, the same as
    the two removals above).

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
    if jail.channel_directory is not None:
        try:
            directories.remove(str(jail.channel_directory))
        except OSError:
            pass
    if jail.channel_namespace_fd is not None:
        _close_namespace_fd(jail.channel_namespace_fd)
    if state is not GroupState.GONE:
        raise JailTeardownFailed(jail.process)
