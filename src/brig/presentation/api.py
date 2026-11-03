"""What an embedder calls for any jail type: reserve channels, wait for one to be ready, wait for
the command's exit, interrupt it, tear the jail down. Creating a jail is each jail type's own
(`presentation/drivers/<type>.py`)."""

import signal
import time
from pathlib import Path
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
from brig.infra import placeholders as _placeholders
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
    PROCESSES,
    Jail,
    close_namespace_fd,
    resolved_state_dir,
)
from brig.presentation.ports import (
    ChannelDirectoryPort,
    ChannelJailFinished,
    ChannelNotReady,
    ChannelReadinessPort,
    ChannelReady,
    ChannelRefused,
    ProcessPort,
    SupervisorPort,
)

_DEFAULT_WAIT_TIMEOUT_S = 30.0
"""How long `run_jail` waits for the command's exit when the embedder names no `timeout_s`."""

_DEFAULT_KILL_GRACE_S = 1.0
"""How long `destroy_jail`'s post-KILL rung polls for the group to be gone, by default."""

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
    `StateDirectoryInvalid` for a bad `BRIG_HOME`.

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
            `channel_directory` are both `None`).
    """
    if jail.channel_namespace_fd is None and jail.channel_directory is not None:
        return ChannelJailFinished()
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
    kill_grace_s: float = _DEFAULT_KILL_GRACE_S,
    processes: ProcessPort = PROCESSES,
    supervisors: SupervisorPort | None = None,
    directories: ChannelDirectoryPort = CHANNEL_DIRECTORIES,
) -> None:
    """Tear `jail` down, verified: no process of its group is left when this returns.

    `kill_grace_s` bounds the post-KILL rung's poll. Then, whatever the ladder found, it closes
    the supervisor's pipe, deletes the supervisor script and the channel directory, and closes
    the namespace fd, swallowing `OSError` from each, so a repeated call is safe. Deleting the
    script after a failed teardown is safe: by then the supervisor has read it or never will
    (TASK-0012). Placeholders are released only once the group is verified gone, since removing
    one a jail still mounts over detaches that mount (TASK-0027).

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
        close_namespace_fd(jail.channel_namespace_fd)
    if state is not GroupState.GONE:
        raise JailTeardownFailed(jail.process)
    if jail.placeholders is not None:
        try:
            _placeholders.release(Path(resolved_state_dir()), jail.placeholders)
        except OSError:
            pass  # left for the next jail's release to sweep


def interrupt_jail(jail: Jail) -> bool:
    """Send `SIGINT` to `jail`'s supervisor, which forwards it to the command (TASK-0020), and
    say whether it was sent: `False` once the command has finished. The command decides what an
    interrupt means; the jail keeps running until `destroy_jail`."""
    return _sockets.signal_jail_pid1(jail.process.pid, signal.SIGINT)
