"""What every jail type's presentation shares: the `Jail` an embedder holds, brig's state
directory, and the real ports' default wiring onto infra (decision-0001 rule 13: no infra type
crosses a port)."""

import functools
import os
import secrets
import signal
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from brig.domain.effects import Process
from brig.domain.jail_types import bwrap
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
from brig.infra.supervisor import link
from brig.presentation.errors import (
    StateDirectoryInvalid,
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


@functools.cache
def resolved_state_dir() -> str:
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


PROCESSES: ProcessPort = _RealProcesses()


@dataclass(frozen=True)
class _RealSupervisors:
    """A `LiveSupervisors` instance's own methods, as the `SupervisorPort` an
    embedder gets by default -- `await_done` through `real_supervisor_port`'s
    thin adapter, which translates infra's `SupervisorDoneUnknown` into the
    port's, mirroring `_RealProcesses`'s own `reap`/`reap_deadline` adapters.
    """

    start: Callable[[tuple[str, ...], tuple[tuple[str, str], ...]], link.Supervisor]
    await_done: Callable[[int, float], int | None | SupervisorDoneUnknown]
    close: Callable[[int], None]


def real_supervisor_port(live: link.LiveSupervisors) -> SupervisorPort:
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


def _allocate_channel_directory() -> str:
    """Name a fresh per-jail channel directory under brig's own state directory
    (`resolved_state_dir`), never `/tmp` -- a random component per call, so no two
    jails share one. Creates nothing -- `_RealChannelDirectories.create` does, later,
    in `create_bwrap_jail` (TASK-0001.26). `resolved_state_dir` raises `StateDirectoryInvalid`
    should `BRIG_HOME` name a value brig cannot use.
    """
    return f"{resolved_state_dir()}/channels/{secrets.token_hex(8)}"


@dataclass(frozen=True)
class _RealChannelDirectories:
    """The `ChannelDirectoryPort` an embedder gets by default: data (one function),
    the same shape `_RealProcesses` gives `ProcessPort`.
    """

    allocate: Callable[[], str] = _allocate_channel_directory
    create: Callable[[str], None] = _sockets.create
    remove: Callable[[str], None] = _sockets.remove


CHANNEL_DIRECTORIES: ChannelDirectoryPort = _RealChannelDirectories()


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


CHANNEL_READINESS: ChannelReadinessPort = _RealChannelReadiness()


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
    namespace was ever looked up, and there is nothing to compare -- *or*, with
    `channel_directory` set, when the jail's command had already finished by the
    time it was looked up (TASK-0001.30): its namespace was gone, so there is none
    to hold, and `await_channel_ready` answers `ChannelJailFinished`. The fd is the
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
    mounts: tuple[bwrap.Mount, ...] = ()
    placeholders: Path | None = None


def close_namespace_fd(fd: int) -> None:
    """Close `fd`, swallowing `OSError`, the same way every other teardown cleanup
    in this module does: an already-closed fd is fine, and nothing that runs after
    teardown's own verify should raise over it.
    """
    try:
        os.close(fd)
    except OSError:
        pass
