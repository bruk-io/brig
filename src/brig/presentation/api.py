"""What an embedder calls for any jail type: reserve channels, wait for one to be ready, wait for
the command's exit, tear the jail down (decision-0001). Creating a jail is each jail type's own
(`presentation/drivers/<type>.py`)."""

import time
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
from brig.domain.effects import ExitCodeUnknown, GroupState
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


def reserve_channels(
    channels: tuple[Channel, ...],
    *,
    directories: ChannelDirectoryPort = CHANNEL_DIRECTORIES,
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
    should `BRIG_HOME` name a value brig cannot use (`resolved_state_dir`).

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


def await_channel_ready(
    jail: Jail,
    reservation: Reservation,
    *,
    timeout_s: float = _DEFAULT_CHANNEL_READY_TIMEOUT_S,
    readiness: ChannelReadinessPort = CHANNEL_READINESS,
    processes: ProcessPort = PROCESSES,
) -> ChannelReady | ChannelNotReady | ChannelRefused | ChannelJailFinished:
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

    A jail whose command had already finished when `create_bwrap_jail` looked for its
    namespace (`channel_directory` set, `channel_namespace_fd` `None`, TASK-0001.30)
    answers `ChannelJailFinished` at once, before any connect: nothing in it can
    listen, and a connect with no namespace to verify against would trust whatever
    host process answered at that path. One that finishes later, after the scan held
    its namespace, answers the same as soon as an attempt reads not ready and
    `processes.peek` shows the jail's own process has exited (TASK-0023): peeked, never
    reaped (decision-0003), so `run_jail` and `destroy_jail` still find it.

    `jail.channel_namespace_fd` is `None` with no `channel_directory` for a jail that
    declared no channel, and
    that is a caller precondition violation rather than an outcome: there is no
    namespace to verify against, and the reservation being asked about cannot have
    come from that jail's `reserve_channels` call. Checked explicitly, rather than
    left to whatever `readiness.ready` would do with a `None` fd (a real
    `ChannelReadinessPort` would format it into a path string and read a confusing
    `FileNotFoundError` back) -- mypy strict would refuse this call unchecked too,
    since the port's own contract takes `int`, never `int | None`.

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
    processes: ProcessPort = PROCESSES,
    supervisors: SupervisorPort | None = None,
    directories: ChannelDirectoryPort = CHANNEL_DIRECTORIES,
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
    once this jail is gone (`close_namespace_fd` swallows `OSError`, the same as
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
        close_namespace_fd(jail.channel_namespace_fd)
    if state is not GroupState.GONE:
        raise JailTeardownFailed(jail.process)
