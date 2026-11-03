"""What every jail type's presentation shares: the `Jail` an embedder holds, brig's state
directory, the real ports' wiring onto infra, which translates infra's values so none crosses a
port (decision-0001 rule 13), and `dismantle`, the one cleanup a failed create and
`destroy_jail` both run (TASK-0044)."""

import functools
import os
import secrets
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from brig.domain import operations
from brig.domain.claims import Claim
from brig.domain.effects import ExitCodeUnknown, ExitOutcome, GroupState, Process
from brig.domain.grades import Grade
from brig.domain.jail_types import bwrap
from brig.infra import placeholders as _placeholders
from brig.infra import sockets as _sockets
from brig.infra import state_dir as _state_dir_mod
from brig.infra.processes import ProcessUnknown as _InfraProcessUnknown
from brig.infra.processes import group_alive as _group_alive
from brig.infra.processes import group_alive_deadline as _group_alive_deadline
from brig.infra.processes import peek as _infra_peek
from brig.infra.processes import release as _release
from brig.infra.processes import signal_group as _signal_group
from brig.infra.supervisor import link
from brig.presentation.driver import run
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
    PlaceholderPort,
    ProcessPort,
    SupervisorPort,
)

KILL_GRACE_S = 1.0
"""How long teardown's post-KILL rung polls for the group to be gone, by default."""


def _peek(pid: int) -> int | None | ExitCodeUnknown:
    """infra's `peek`, its `ProcessUnknown` translated into domain's `ExitCodeUnknown`."""
    result = _infra_peek(pid)
    return ExitCodeUnknown() if isinstance(result, _InfraProcessUnknown) else result


@functools.cache
def resolved_state_dir() -> str:
    """brig's state directory (`BRIG_HOME`, else `~/.brig`), created if absent, resolved once
    per process. A string, since it crosses into the domain.

    Raises:
        StateDirectoryInvalid: `BRIG_HOME` is not an absolute path.
    """
    try:
        resolved = _state_dir_mod.resolve()
    except ValueError as exc:
        raise StateDirectoryInvalid(str(exc)) from exc
    return str(_state_dir_mod.ensure(resolved))


@dataclass(frozen=True)
class _RealProcesses:
    """`brig.infra.processes` as the default `ProcessPort`."""

    signal_group: Callable[[int, signal.Signals], None] = _signal_group
    peek: Callable[[int], int | None | ExitCodeUnknown] = _peek
    release: Callable[[int], None] = _release
    group_alive: Callable[[int, frozenset[int]], bool] = _group_alive
    group_alive_deadline: Callable[[int, int, float], bool] = _group_alive_deadline


PROCESSES: ProcessPort = _RealProcesses()


@dataclass(frozen=True)
class _RealSupervisor:
    """A `LiveSupervisor` as a `SupervisorPort`."""

    start: Callable[[tuple[str, ...], frozendict[str, str]], link.Supervisor]
    await_done: Callable[[int, float], ExitOutcome]
    close: Callable[[int], None]


def real_supervisor_port(live: link.LiveSupervisor) -> SupervisorPort:
    """`live` as a `SupervisorPort`, its `SupervisorDoneUnknown` translated into domain's
    `ExitCodeUnknown`."""

    def await_done(pid: int, deadline: float) -> ExitOutcome:
        outcome = live.await_done(pid, deadline)
        return ExitCodeUnknown() if isinstance(outcome, link.SupervisorDoneUnknown) else outcome

    return _RealSupervisor(start=live.start, await_done=await_done, close=live.close)


def _allocate_channel_directory() -> str:
    """A fresh channel directory path under brig's state directory, random per call; creates
    nothing. `resolved_state_dir` raises `StateDirectoryInvalid` for a bad `BRIG_HOME`."""
    return f"{resolved_state_dir()}/channels/{secrets.token_hex(8)}"


@dataclass(frozen=True)
class _RealChannelDirectories:
    """`brig.infra.sockets` as the default `ChannelDirectoryPort`."""

    allocate: Callable[[], str] = _allocate_channel_directory
    create: Callable[[str], None] = _sockets.create
    remove: Callable[[str], None] = _sockets.remove


CHANNEL_DIRECTORIES: ChannelDirectoryPort = _RealChannelDirectories()


def _channel_ready(
    path: str, jail_namespace_fd: int
) -> ChannelReady | ChannelNotReady | ChannelRefused:
    """infra's `channel_ready`, its values translated into this port's; a ready outcome's
    connection passes through, still open.

    `isinstance`, not `match`: pypeeker cannot resolve a class pattern reached through a module
    alias (`case _sockets.X()`), and reports `X` as unused (measured)."""
    outcome = _sockets.channel_ready(path, jail_namespace_fd)
    if isinstance(outcome, _sockets.ChannelReady):
        return ChannelReady(outcome.connection)
    if isinstance(outcome, _sockets.ChannelNotReady):
        return ChannelNotReady()
    if isinstance(outcome, _sockets.ChannelRefused):
        return ChannelRefused(ChannelReadinessRefusal(outcome.reason))
    assert_never(outcome)


@dataclass(frozen=True)
class _RealChannelReadiness:
    """`_channel_ready` as the default `ChannelReadinessPort`."""

    ready: Callable[[str, int], ChannelReady | ChannelNotReady | ChannelRefused] = _channel_ready


CHANNEL_READINESS: ChannelReadinessPort = _RealChannelReadiness()


def _hold_placeholders(paths: tuple[str, ...]) -> str | None:
    """infra's `hold` under brig's state directory, for a fresh jail id; `None` for no paths,
    so a jail with nothing absent writes no record."""
    if not paths:
        return None
    return str(_placeholders.hold(Path(resolved_state_dir()), secrets.token_hex(8), paths))


def _attach_placeholders(record: str, pid: int) -> None:
    """infra's `attach` under brig's state directory."""
    _placeholders.attach(Path(resolved_state_dir()), Path(record), pid)


def _release_placeholders(record: str) -> None:
    """infra's `release` under brig's state directory."""
    _placeholders.release(Path(resolved_state_dir()), Path(record))


@dataclass(frozen=True)
class _RealPlaceholders:
    """`brig.infra.placeholders` as the default `PlaceholderPort`."""

    hold: Callable[[tuple[str, ...]], str | None] = _hold_placeholders
    attach: Callable[[str, int], None] = _attach_placeholders
    release: Callable[[str], None] = _release_placeholders


PLACEHOLDERS: PlaceholderPort = _RealPlaceholders()


@dataclass(frozen=True)
class Jail:
    """A bwrap jail an embedder created.

    `process` is the supervisor's identity (decision-0002), and `supervisors` the port it was
    started through, the only one that can read or close its events pipe. `supervisor_script`,
    `channel_directory` and `placeholders` are what `destroy_jail` removes (`None` when nothing
    was made, as for a `Jail` built directly or with a caller's own `supervisors`).
    `channel_namespace_fd` is an open fd on the jail's PID namespace that readiness compares a
    peer against, held so its inode cannot be recycled (decision-0005 item 1); `None` with no
    channel, or with `channel_directory` set when the command had finished before the namespace
    was found. `mounts` is what the jail was compiled with and `report` its ceiling per claim
    (decision-0008).
    """

    process: Process
    supervisors: SupervisorPort
    supervisor_script: Path | None = None
    channel_directory: Path | None = None
    channel_namespace_fd: int | None = None
    mounts: tuple[bwrap.Mount, ...] = ()
    placeholders: str | None = None
    report: frozendict[Claim, Grade] = frozendict()


def _close_namespace_fd(fd: int) -> None:
    """Close `fd`, swallowing `OSError`: teardown cleanup never raises past its verify."""
    try:
        os.close(fd)
    except OSError:
        pass


def dismantle(
    process: Process | None,
    *,
    supervisors: SupervisorPort,
    processes: ProcessPort,
    directories: ChannelDirectoryPort,
    placeholders: PlaceholderPort,
    kill_grace_s: float = KILL_GRACE_S,
    supervisor_script: Path | None = None,
    channel_directory: Path | None = None,
    channel_namespace_fd: int | None = None,
    placeholder_record: str | None = None,
) -> GroupState:
    """Tear down what a jail made, and return what teardown found: the one cleanup `destroy_jail`
    and a failed `create_bwrap_jail` both run, so the two cannot disagree (TASK-0044).

    Once a process exists, it goes first: the verified kill ladder (`operations.destroy`, its
    post-KILL poll bounded by `kill_grace_s`), then the supervisor's pipe is closed. With no
    process (a create that failed before its start) there is nothing to tear down and the result
    is `GroupState.GONE`. Then, whatever the ladder found, the supervisor script and the channel
    directory are removed and the namespace fd closed, swallowing `OSError` from each, so a
    repeated call is safe; removing the script after a failed teardown is safe, since by then the
    supervisor has read it or never will (TASK-0012). The placeholder record is released only
    when the result is `GONE`: removing a placeholder a jail still mounts over detaches that
    mount (TASK-0027), so a record a live jail holds is left for a later sweep. Raises nothing;
    the caller decides what an `ALIVE` result becomes.
    """
    state = GroupState.GONE
    if process is not None:
        deadline = time.monotonic() + kill_grace_s
        state = run(operations.destroy(process, deadline=deadline), processes, supervisors)
        supervisors.close(process.pid)
    if supervisor_script is not None:
        try:
            supervisor_script.unlink(missing_ok=True)
        except OSError:
            pass
    if channel_directory is not None:
        try:
            directories.remove(str(channel_directory))
        except OSError:
            pass
    if channel_namespace_fd is not None:
        _close_namespace_fd(channel_namespace_fd)
    if state is GroupState.GONE and placeholder_record is not None:
        try:
            placeholders.release(placeholder_record)
        except OSError:
            pass  # left for the next jail's release to sweep
    return state
