"""What an embedder calls for any jail type: reserve channels, wait for one to be ready, wait for
the command's exit, interrupt it, tear the jail down. Creating a jail is each jail type's own
(`presentation/drivers/<type>.py`)."""

import signal
import time
from typing import assert_never

from brig.domain import channels as _channels
from brig.domain import operations
from brig.domain.channels import (
    Channel,
    ChannelDirectory,
    ChannelNameRefusal,
    Reservation,
    Reservations,
)
from brig.domain.effects import ExitCodeUnknown, GroupState
from brig.infra import sockets as _sockets
from brig.presentation.driver import run
from brig.presentation.errors import (
    ChannelNameRefused,
    JailExitUnknown,
    JailTeardownFailed,
    JailWaitTimedOut,
)
from brig.presentation.jail import (
    CHANNEL_DIRECTORIES,
    CHANNEL_READINESS,
    KILL_GRACE_S,
    PLACEHOLDERS,
    PROCESSES,
    Jail,
    dismantle,
)
from brig.presentation.ports import (
    ChannelDirectoryPort,
    ChannelJailFinished,
    ChannelNotReady,
    ChannelReadinessPort,
    ChannelReady,
    ChannelRefused,
    PlaceholderPort,
    ProcessPort,
    SupervisorPort,
)

_DEFAULT_WAIT_TIMEOUT_S = 30.0
"""How long `run_jail` waits for the command's exit when the embedder names no `timeout_s`."""

_DEFAULT_CHANNEL_READY_TIMEOUT_S = 30.0
"""How long `await_channel_ready` polls when the embedder names no `timeout_s`."""

_CHANNEL_READY_POLL_INTERVAL_S = 0.05
"""The pause between readiness attempts: each is a connect and several `/proc` reads."""


def reserve_channels(
    channels: tuple[Channel, ...],
    *,
    directories: ChannelDirectoryPort = CHANNEL_DIRECTORIES,
) -> Reservations:
    """Reserve each of `channels` for a jail not yet created, so the embedder can write each
    `Reservation.endpoint` into the command's argv (never env, old SPEC decision-184/186) and
    then pass these `Reservations` to `create_bwrap_jail`. `directories` names the channel
    directory; by default a fresh path under brig's state directory, whose resolution raises
    `StateDirectoryInvalid` for a bad `BRIG_HOME`, and `StateDirectoryWriteFailed` when the
    host refuses to make it.

    Raises:
        ChannelNameRefused: a channel's name would escape or repeat in the channel
            directory (`domain/channels.py`'s `reserve`).
    """
    host_path = directories.allocate()
    directory = ChannelDirectory(host_path=host_path, jail_path=host_path)
    match _channels.reserve(channels, directory):
        case Reservations() as reservations:
            return reservations
        case ChannelNameRefusal(name=name):
            raise ChannelNameRefused(name)
        case _ as unreachable:
            assert_never(unreachable)


def await_channel_ready(
    jail: Jail,
    reservation: Reservation,
    *,
    timeout_s: float = _DEFAULT_CHANNEL_READY_TIMEOUT_S,
    readiness: ChannelReadinessPort = CHANNEL_READINESS,
    processes: ProcessPort = PROCESSES,
) -> ChannelReady | ChannelNotReady | ChannelRefused | ChannelJailFinished:
    """Poll a verified connect to `reservation`'s channel (decision-0005) until it reads ready or
    refused, or `timeout_s` passes, and return the last outcome.

    Each attempt opens `reservation.name` beneath the fd `jail` holds on its own channel
    directory, through no link, and connects without blocking, so no attempt outlasts the
    deadline by more than its own few reads, however the jail listens; a symbolic link at the
    name is refused as `PEER_OUTSIDE_JAIL` without the embedder dialling what it names
    (TASK-0045).

    `ChannelReady` carries the verified connection, open: the embedder uses it, owns it and
    closes it, and never dials `reservation.bound_path` itself, since the jail can swap its
    socket for a symbolic link to a host socket once readiness has passed (TASK-0001.34). Only
    the attempt that returns `ChannelReady` leaves a socket open; every other attempt closed its
    own. A second connection needs a second call.

    `ChannelReady` and `ChannelRefused` return at once; a refusal is about this connection, so
    one that reconnects verifies again. `ChannelNotReady` is retried until the deadline, checked
    between attempts. `ChannelJailFinished` comes back at once for a jail whose command finished
    before its namespace was found, and as soon as an attempt reads not ready and
    `processes.peek` shows the jail's process has exited (TASK-0023); peeked, never reaped, so
    `run_jail` and `destroy_jail` still find it.

    Raises:
        ValueError: the jail declared no channel (`channel_namespace_fd` and
            `channel_directory` are both `None`), or holds no `channel_directory_fd`.
    """
    if jail.channel_namespace_fd is None and jail.channel_directory is not None:
        return ChannelJailFinished()
    if jail.channel_namespace_fd is None or jail.channel_directory_fd is None:
        raise ValueError(
            "jail declared no channel: await_channel_ready has no channel directory to open "
            "the reservation beneath, or no namespace to verify a peer against"
        )
    deadline = time.monotonic() + timeout_s
    while True:
        outcome = readiness.ready(
            jail.channel_directory_fd, reservation.name, jail.channel_namespace_fd
        )
        if not isinstance(outcome, ChannelNotReady):
            return outcome
        if processes.peek(jail.process.pid) is not None:
            return ChannelJailFinished()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return outcome
        time.sleep(min(_CHANNEL_READY_POLL_INTERVAL_S, remaining))


def run_jail(
    jail: Jail,
    *,
    timeout_s: float = _DEFAULT_WAIT_TIMEOUT_S,
    processes: ProcessPort = PROCESSES,
    supervisors: SupervisorPort | None = None,
) -> int:
    """Wait up to `timeout_s` for `jail`'s supervisor to report its command's exit code, and
    return it. `supervisors` defaults to `jail.supervisors`, the port its supervisor was started
    through.

    Raises:
        JailWaitTimedOut: the command did not finish within `timeout_s`. The jail still runs:
            call `run_jail` again to keep waiting, or `destroy_jail`.
        JailExitUnknown: the supervisor's report can never be recovered; waiting again will
            not help.
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
    kill_grace_s: float = KILL_GRACE_S,
    processes: ProcessPort = PROCESSES,
    supervisors: SupervisorPort | None = None,
    directories: ChannelDirectoryPort = CHANNEL_DIRECTORIES,
    placeholders: PlaceholderPort = PLACEHOLDERS,
) -> None:
    """Tear `jail` down, verified: no process of its group is left when this returns.

    Runs `dismantle`, the cleanup a failed `create_bwrap_jail` runs too (TASK-0044):
    `kill_grace_s` bounds the post-KILL rung's poll; then, whatever the ladder found, it closes
    the supervisor's pipe, deletes the supervisor script and the channel directory, and closes
    the namespace and channel directory fds, swallowing `OSError` from each, so a repeated call
    is safe. Placeholders are released only once the group is verified gone, since removing one
    a jail still mounts over detaches that mount (TASK-0027). A failure to close the
    supervisor's pipe is swallowed the same way: it says nothing of whether the group is gone.

    Raises:
        JailTeardownFailed: the kill ladder's last verify still found the group alive, or the
            ladder itself raised, so the group was never verified gone; then that error is the
            `__cause__` (TASK-0046).
    """
    dismantled = dismantle(
        jail.process,
        supervisors=supervisors if supervisors is not None else jail.supervisors,
        processes=processes,
        directories=directories,
        placeholders=placeholders,
        kill_grace_s=kill_grace_s,
        supervisor_script=jail.supervisor_script,
        channel_directory=jail.channel_directory,
        channel_namespace_fd=jail.channel_namespace_fd,
        channel_directory_fd=jail.channel_directory_fd,
        placeholder_record=jail.placeholders,
    )
    if dismantled.state is not GroupState.GONE:
        raise JailTeardownFailed(jail.process) from dismantled.ladder_error


def interrupt_jail(jail: Jail) -> bool:
    """Send `SIGINT` to `jail`'s supervisor, which forwards it to the command (TASK-0020), and
    say whether it was sent: `False` once the command has finished. The command decides what an
    interrupt means; the jail keeps running until `destroy_jail`."""
    return _sockets.signal_jail_pid1(jail.process.pid, signal.SIGINT)
