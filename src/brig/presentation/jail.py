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
from brig.domain.jail_types import bwrap, seatbelt
from brig.domain.policy.egress import (
    Destination,
    EgressChangeKind,
    EgressPolicy,
    EgressReason,
    EgressVerdict,
)
from brig.domain.policy.egress_record import EgressChange, EgressDecision, EgressRecord
from brig.infra import log as _log
from brig.infra import members as _members
from brig.infra import placeholders as _placeholders
from brig.infra import sockets as _sockets
from brig.infra import state_dir as _state_dir_mod
from brig.infra.processes import ProcessUnknown as _InfraProcessUnknown
from brig.infra.processes import group_alive as _group_alive
from brig.infra.processes import group_alive_deadline as _group_alive_deadline
from brig.infra.processes import peek as _infra_peek
from brig.infra.processes import release as _release
from brig.infra.processes import signal_group as _signal_group
from brig.infra.proxy import launch as _launch
from brig.infra.proxy import program as _proxy_program
from brig.infra.supervisor import link
from brig.presentation.driver import run
from brig.presentation.errors import (
    JailEgressEnded,
    StateDirectoryInvalid,
    StateDirectoryWriteFailed,
)
from brig.presentation.ports import (
    ChannelDirectoryPort,
    ChannelNotReady,
    ChannelReadinessPort,
    ChannelReadinessRefusal,
    ChannelReady,
    ChannelRefused,
    EgressPort,
    MembersPort,
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
        StateDirectoryWriteFailed: the host refused to make it (TASK-0046).
    """
    try:
        resolved = _state_dir_mod.resolve()
    except ValueError as exc:
        raise StateDirectoryInvalid(str(exc)) from exc
    try:
        return str(_state_dir_mod.ensure(resolved))
    except OSError as exc:
        raise StateDirectoryWriteFailed(str(resolved)) from exc


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


def _decision(line: str) -> EgressDecision | None:
    """One decision line the proxy wrote, as an `EgressDecision`; `None` for a line that is not
    one (unreadable, another event, or a field of the wrong kind), which is dropped like a line
    the link could not keep, and shows as a gap in `seq`."""
    try:
        read = _log.decode(line)
    except _log.LineUnreadable:
        return None
    if read.source != _proxy_program.SOURCE or read.event != _proxy_program.DECISION_EVENT:
        return None
    seq, verdict, host, port, reason, address = (
        read.fields.get(name) for name in ("seq", "verdict", "host", "port", "reason", "address")
    )
    if not (
        isinstance(seq, int)
        and isinstance(port, int)
        and isinstance(host, str)
        and isinstance(verdict, str)
        and isinstance(reason, str)
        and isinstance(address, str)
    ):
        return None
    try:
        return EgressDecision(
            seq=seq,
            verdict=EgressVerdict(verdict),
            destination=Destination(host, port),
            reason=EgressReason(reason),
            address=address,
            time=read.time,
            line=line,
        )
    except ValueError:
        return None


@dataclass(frozen=True)
class _RealEgress:
    """A `LiveSupervisor`'s egress proxy as an `EgressPort`."""

    change: Callable[[EgressChangeKind, Destination], None]
    record: Callable[[], EgressRecord]
    decisions: Callable[[], tuple[EgressDecision, ...]]


def real_egress_port(live: link.LiveSupervisor) -> EgressPort:
    """The egress proxy `live` starts as an `EgressPort`, its plain data translated into the
    domain's values and its `ProxyEnded` into `JailEgressEnded`. Read through `live.proxy` at
    each call, since the proxy starts with the supervisor; before that, the record is empty and
    a change is refused as ended."""

    def change(kind: EgressChangeKind, destination: Destination) -> None:
        proxy = live.proxy
        if proxy is None:
            raise JailEgressEnded(destination)
        try:
            proxy.change(kind.value, destination.host, destination.port)
        except _launch.ProxyEnded as error:
            raise JailEgressEnded(destination) from error

    def record() -> EgressRecord:
        proxy = live.proxy
        if proxy is None:
            return EgressRecord(EgressPolicy())
        return EgressRecord(
            created=EgressPolicy(tuple(Destination(host, port) for host, port in proxy.allow)),
            changes=tuple(
                EgressChange(EgressChangeKind(kind), Destination(host, port), when)
                for kind, host, port, when in proxy.changes
            ),
        )

    def decisions() -> tuple[EgressDecision, ...]:
        proxy = live.proxy
        if proxy is None:
            return ()
        read = (_decision(line) for line in proxy.take_lines())
        return tuple(decision for decision in read if decision is not None)

    return _RealEgress(change=change, record=record, decisions=decisions)


def _allocate_channel_directory() -> str:
    """A fresh channel directory path under brig's state directory, random per call; creates
    nothing but brig's state directory itself: `resolved_state_dir` raises
    `StateDirectoryInvalid` for a bad `BRIG_HOME`, and `StateDirectoryWriteFailed` when the host
    refuses to make it."""
    return f"{resolved_state_dir()}/channels/{secrets.token_hex(8)}"


@dataclass(frozen=True)
class _RealChannelDirectories:
    """`brig.infra.sockets` as the default `ChannelDirectoryPort`."""

    allocate: Callable[[], str] = _allocate_channel_directory
    create: Callable[[str], None] = _sockets.create
    remove: Callable[[str], None] = _sockets.remove


CHANNEL_DIRECTORIES: ChannelDirectoryPort = _RealChannelDirectories()


def _channel_ready(
    directory_fd: int, name: str, jail_namespace_fd: int
) -> ChannelReady | ChannelNotReady | ChannelRefused:
    """infra's `channel_ready`, its values translated into this port's; a ready outcome's
    connection passes through, still open.

    `isinstance`, not `match`: pypeeker cannot resolve a class pattern reached through a module
    alias (`case _sockets.X()`), and reports `X` as unused (measured)."""
    outcome = _sockets.channel_ready(directory_fd, name, jail_namespace_fd)
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

    ready: Callable[[int, str, int], ChannelReady | ChannelNotReady | ChannelRefused] = (
        _channel_ready
    )


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
class _RealMembers:
    """`MembersPort` onto infra's `members`."""

    kill: Callable[[str, str, float], bool] = _members.kill_members


MEMBERS: MembersPort = _RealMembers()


def member_decoy(mark: Path) -> Path:
    """The decoy beside a Seatbelt jail's member `mark`: a file its profile refuses, as every
    file of the state directory but the jail's own, so a broader sandbox that allows the mark
    is told apart (`infra.members`)."""
    return mark.with_suffix(".decoy")


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
    was found. `channel_directory_fd` is an fd on the channel directory, opened right after it
    was made and held for the jail's lifetime, beneath which readiness opens each channel's name
    (TASK-0045); `None` with no channel. `mounts` is what the jail was compiled with and
    `report` its ceiling per claim (decision-0008). `egress` is the port to the jail's egress
    proxy (decision-0009 items 5 and 6), `None` for a jail with none. `member_mark` is a Seatbelt
    jail's mark (with its decoy beside it, `member_decoy`), which `destroy_jail` finds every
    process of the jail by and removes once none is left; `None` for any other jail.
    """

    process: Process
    supervisors: SupervisorPort
    supervisor_script: Path | None = None
    channel_directory: Path | None = None
    channel_namespace_fd: int | None = None
    channel_directory_fd: int | None = None
    mounts: tuple[bwrap.Mount, ...] = ()
    rules: tuple[seatbelt.Rule, ...] = ()
    placeholders: str | None = None
    report: frozendict[Claim, Grade] = frozendict()
    egress: EgressPort | None = None
    member_mark: Path | None = None


def _close_fd(fd: int) -> None:
    """Close `fd`, swallowing `OSError`: teardown cleanup never raises past its verify."""
    try:
        os.close(fd)
    except OSError:
        pass


@dataclass(frozen=True)
class _Dismantled:
    """What `dismantle` found (TASK-0046). `state` is the group as the kill ladder's last verify
    read it, or `GroupState.ALIVE` when the ladder itself raised `ladder_error`, since the group
    was then never verified gone. `close_error` is what closing the supervisor's pipe raised.
    Each is `None` when nothing raised, and is the caller's to attach to what it raises."""

    state: GroupState
    ladder_error: Exception | None = None
    close_error: Exception | None = None


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
    channel_directory_fd: int | None = None,
    placeholder_record: str | None = None,
    member_mark: Path | None = None,
    members: MembersPort = MEMBERS,
) -> _Dismantled:
    """Tear down what a jail made, and return what teardown found: the one cleanup `destroy_jail`
    and a failed `create_bwrap_jail` both run, so the two cannot disagree (TASK-0044).

    Once a process exists, it goes first: the verified kill ladder (`operations.destroy`, its
    post-KILL poll bounded by `kill_grace_s`), then the supervisor's pipe is closed. With no
    process (a create that failed before its spawn) there is nothing to tear down and the state
    is `GroupState.GONE`. Then, whatever the ladder found, the supervisor script and the channel
    directory are removed and the namespace and channel directory fds closed, swallowing
    `OSError` from each, so a repeated call is safe; removing the script after a failed teardown
    is safe, since by then the supervisor has read it or never will (TASK-0012). The placeholder
    record is released only when the state is `GONE`: removing a placeholder a jail still
    mounts over detaches that mount (TASK-0027), so a record a live jail holds is left for a
    later sweep.

    With `member_mark` (a Seatbelt jail), once the ladder has run, `members` kills every process
    that carries the jail's profile, however it left the group, polling until none is left or a
    further `kill_grace_s` passes; one left makes the state `ALIVE`. The mark and its decoy are
    removed only once the state is `GONE`, since a process that carries the profile is found by
    them and by nothing else.

    Raises nothing, so it never hides the error of a failed step that called it (TASK-0046): an
    exception from the ladder makes the state `ALIVE` (the group was not verified gone), and it
    and one from the close are returned on the `_Dismantled`, the rest of the cleanup still run.
    The caller decides what they become: `create_bwrap_jail` adds each to the step's error as a
    note, and raises `JailTeardownFailed` from that error on an `ALIVE` state; `destroy_jail`
    raises `JailTeardownFailed` from the ladder's error on an `ALIVE` state, and swallows the
    close's, as it does every other cleanup's.
    """
    state = GroupState.GONE
    ladder_error: Exception | None = None
    close_error: Exception | None = None
    if process is not None:
        deadline = time.monotonic() + kill_grace_s
        try:
            state = run(operations.destroy(process, deadline=deadline), processes, supervisors)
        except Exception as error:
            state = GroupState.ALIVE
            ladder_error = error
        if member_mark is not None:
            sweep_deadline = time.monotonic() + kill_grace_s
            try:
                gone = members.kill(
                    str(member_mark), str(member_decoy(member_mark)), sweep_deadline
                )
            except Exception as error:
                gone = False
                ladder_error = ladder_error or error
            if not gone:
                state = GroupState.ALIVE
        try:
            supervisors.close(process.pid)
        except Exception as error:
            close_error = error
    if supervisor_script is not None:
        try:
            supervisor_script.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            supervisor_script.with_suffix(".sb").unlink(missing_ok=True)
        except OSError:
            pass
    if channel_directory is not None:
        try:
            directories.remove(str(channel_directory))
        except OSError:
            pass
    for fd in (channel_namespace_fd, channel_directory_fd):
        if fd is not None:
            _close_fd(fd)
    if state is GroupState.GONE and member_mark is not None:
        for made in (member_mark, member_decoy(member_mark)):
            try:
                made.unlink(missing_ok=True)
            except OSError:
                pass
    if state is GroupState.GONE and placeholder_record is not None:
        try:
            placeholders.release(placeholder_record)
        except OSError:
            pass  # left for the next jail's release to sweep
    return _Dismantled(state, ladder_error, close_error)
