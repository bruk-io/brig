"""What every jail type's presentation shares: the `Jail` an embedder holds, brig's state
directory, and the real ports' wiring onto infra, which translates infra's values so none
crosses a port (decision-0001 rule 13)."""

import functools
import os
import secrets
import signal
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from brig.domain.claims import Claim
from brig.domain.effects import ExitCodeUnknown, ExitOutcome, Process
from brig.domain.grades import Grade
from brig.domain.jail_types import bwrap
from brig.infra import sockets as _sockets
from brig.infra import state_dir as _state_dir_mod
from brig.infra.processes import ProcessUnknown as _InfraProcessUnknown
from brig.infra.processes import group_alive as _group_alive
from brig.infra.processes import group_alive_deadline as _group_alive_deadline
from brig.infra.processes import peek as _infra_peek
from brig.infra.processes import release as _release
from brig.infra.processes import signal_group as _signal_group
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
    SupervisorPort,
)


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
    placeholders: Path | None = None
    report: frozendict[Claim, Grade] = frozendict()


def close_namespace_fd(fd: int) -> None:
    """Close `fd`, swallowing `OSError`: teardown cleanup never raises past its verify."""
    try:
        os.close(fd)
    except OSError:
        pass
