"""Channels on the real host: the channel directory's creation and removal, finding and holding
the jail's PID namespace, the verified connect that says a channel is ready (decision-0005), and
signalling the jail's PID 1. Plain data in and out (decision-0001 rule 1).
"""

import errno
import os
import shutil
import signal
import socket
import stat
import struct
import time
from dataclasses import dataclass
from pathlib import Path

SO_PEERPIDFD = getattr(socket, "SO_PEERPIDFD", 77)
"""`SO_PEERPIDFD` (Linux 6.5+), or its kernel ABI number where `socket` has no name for it.
Whether the kernel supports it is learned only by asking (`channel_ready`)."""

_POLL_INTERVAL_S = 0.05
"""How often the PID 1 scans run again: each reads all of `/proc`."""

JAIL_PID1_TIMEOUT_S = 5.0
"""How long to look for the jail's PID 1, measured enough on real bwrap (TASK-0001.24); change
it only against a new measurement. Presentation turns it into the deadline it passes in."""


@dataclass(frozen=True)
class JailPid1NotFound:
    """No in-jail PID 1 appeared under the bwrap process before the deadline, with bwrap still
    running."""


@dataclass(frozen=True)
class JailPid1Exited:
    """No in-jail PID 1 was found and the bwrap process is gone or a zombie: the jail's command
    finished first, taking the namespace with it (TASK-0001.30)."""


@dataclass(frozen=True)
class ChannelReady:
    """The connect reached a socket a process inside the jail's PID namespace listens on, and
    `connection` is that connect, still open: the one connection the check vouches for. Whoever
    receives it owns it and closes it (TASK-0001.34)."""

    connection: socket.socket


@dataclass(frozen=True)
class _Verified:
    """`_verify`'s answer when the peer passed: the caller hands the connection out."""


@dataclass(frozen=True)
class ChannelNotReady:
    """The connect failed: nothing listens there yet. Transient."""


@dataclass(frozen=True)
class ChannelRefused:
    """`channel_ready`'s refusal, `reason` one of the three names below. Terminal for this
    connection. Strings, not an `Enum`: `presentation/ports.py` holds the `Enum` an embedder
    matches on.
    """

    reason: str


PEER_OUTSIDE_JAIL = "peer_outside_jail"
"""The listener's PID namespace is not the jail's; a nested one is refused too."""

PEER_LOOKUP_FAILED = "peer_lookup_failed"
"""The listener could not be identified: an `OSError` on its way, or the pid and the pidfd
disagree (a reused pid)."""

KERNEL_UNSUPPORTED = "kernel_unsupported"
"""The kernel has no `SO_PEERPIDFD`; no fallback to `SO_PEERCRED`, whose pid can be reused."""


_SIGNAL_WAIT_S = 5.0
"""How long `signal_jail_pid1` waits for a jail that is still coming up to start its command."""


def _children(pid: int, proc_root: str = "/proc") -> list[int]:
    """`pid`'s direct children, by reading every `<proc_root>/<n>/status` `PPid:` line. An entry
    that vanishes mid-scan is skipped; `proc_root` is `/proc` except in a test."""
    found: list[int] = []
    for entry in os.listdir(proc_root):
        if not entry.isdigit():
            continue
        try:
            with open(f"{proc_root}/{entry}/status") as handle:
                for line in handle:
                    if line.startswith("PPid:") and int(line.split()[1]) == pid:
                        found.append(int(entry))
                        break
        except OSError:
            continue
    return found


def _nspid(pid: int, proc_root: str = "/proc") -> str:
    """`pid`'s `NSpid` line: its pid in each PID namespace, outermost first. Its `OSError` and
    `StopIteration` (no `NSpid:` line) are left to the caller."""
    with open(f"{proc_root}/{pid}/status") as handle:
        return next(line.split(":", 1)[1].strip() for line in handle if line.startswith("NSpid:"))


def _gone(pid: int, proc_root: str = "/proc") -> bool:
    """Whether `pid` has exited: no `/proc` entry, or a zombie. Any other read failure reads as
    still running."""
    try:
        with open(f"{proc_root}/{pid}/status") as handle:
            return any(line.startswith("State:") and line.split()[1] == "Z" for line in handle)
    except FileNotFoundError:
        return True
    except OSError:
        return False


def jail_pid1_namespace(
    bwrap_pid: int,
    deadline: float,
    proc_root: str = "/proc",
) -> int | JailPid1NotFound | JailPid1Exited:
    """An open fd on the jail's PID namespace, found as the child of `bwrap_pid` whose `NSpid`
    ends in 1; `JailPid1NotFound` once `deadline` passes, `JailPid1Exited` as soon as
    `bwrap_pid` is gone with no PID 1 found.

    `bwrap_pid` is the outer bwrap, whose own namespace is the host's (measured,
    TASK-0001.24): comparing peers against it would pass every peer. The fd is held, never read,
    so the namespace's inode cannot be recycled (decision-0005 item 1). The PID 1 is looked for
    before bwrap's exit is checked, so a PID 1 that exists is always found. An unreadable
    candidate is skipped; an `OSError` listing `proc_root` propagates.
    """
    while True:
        for child in _children(bwrap_pid, proc_root):
            try:
                if _nspid(child, proc_root).split()[-1] != "1":
                    continue
                return os.open(f"{proc_root}/{child}/ns/pid", os.O_RDONLY)
            except OSError:
                continue
        if _gone(bwrap_pid, proc_root):
            return JailPid1Exited()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return JailPid1NotFound()
        time.sleep(min(_POLL_INTERVAL_S, remaining))


def _pid1_under(bwrap_pid: int, proc_root: str) -> tuple[int, dict[str, str]] | None:
    """The jail's PID 1 under `bwrap_pid` and its `/proc` status fields, or `None`."""
    for child in _children(bwrap_pid, proc_root):
        try:
            with open(f"{proc_root}/{child}/status") as handle:
                fields = dict(line.split(":", 1) for line in handle if ":" in line)
        except OSError:
            continue
        if fields.get("NSpid", "").split()[-1:] == ["1"]:
            return child, fields
    return None


def signal_jail_pid1(
    bwrap_pid: int,
    sig: int,
    proc_root: str = "/proc",
    timeout_s: float = _SIGNAL_WAIT_S,
) -> bool:
    """Send `sig` to the jail's PID 1 (its supervisor) once it has started the command, and say
    whether it was sent.

    Waits up to `timeout_s` while the jail is still coming up (no PID 1 yet, or a PID 1 with no
    child yet): a jail `create_bwrap_jail` just returned may not have started its command. `False`
    once the jail is gone, its PID 1 a zombie, or a PID 1 that started its command has none left:
    the command has finished.

    Through a pidfd, opened first and the candidate checked again after it (its parent still
    `bwrap_pid`, its innermost pid still 1), so a pid recycled between the scan and the signal is
    never signalled.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        found = _pid1_under(bwrap_pid, proc_root)
        if found is None and _gone(bwrap_pid, proc_root):
            return False
        if found is not None:
            child, fields = found
            if fields.get("State", "").split()[:1] == ["Z"]:
                return False
            if _children(child, proc_root):
                return _signal_checked(bwrap_pid, child, sig, proc_root)
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL_S)


def _signal_checked(bwrap_pid: int, child: int, sig: int, proc_root: str) -> bool:
    """Signal `child` through a pidfd if it is still `bwrap_pid`'s PID 1 once the pidfd is open."""
    try:
        pidfd = os.pidfd_open(child)
    except OSError:
        return False
    try:
        again = _pid1_under(bwrap_pid, proc_root)
        if again is None or again[0] != child:
            return False
        signal.pidfd_send_signal(pidfd, sig)
        return True
    except OSError:
        return False
    finally:
        os.close(pidfd)


def channel_ready(
    path: str, jail_namespace_fd: int, *, so_peerpidfd: int = SO_PEERPIDFD
) -> ChannelReady | ChannelNotReady | ChannelRefused:
    """Connect to `path` once and verify that the process that called `listen()` on the socket
    that answered is in the PID namespace `jail_namespace_fd` names (decision-0005).

    `ChannelReady` carries the verified connection, open, and its receiver owns it: readiness is
    a property of that one connection, and a later dial of `path` follows whatever the jail has
    put there since, a symbolic link to a host socket included (TASK-0001.34). Every other
    outcome, and the one raise, closes the connection first, so only a ready attempt leaves a
    socket open. The socket is blocking and, like every socket Python makes, not inherited by a
    process spawned later.

    A failed connect is `ChannelNotReady`. The peer's pid comes from `SO_PEERCRED`, its pidfd
    from `SO_PEERPIDFD`, its namespace from `/proc/<pid>/ns/pid`, and the pidfd's `fdinfo` must
    name the same pid, so a pid reused in between cannot pass. `ENOPROTOOPT` from
    `SO_PEERPIDFD` is `KERNEL_UNSUPPORTED`; any other `OSError` (measured: `EINVAL` from a
    listener that exited while its child kept the socket) is `PEER_LOOKUP_FAILED`.

    Every outcome is returned. The one raise, `OSError` for a `jail_namespace_fd` that is not
    open, comes from reading it, which is done last, so the refusals above it need no namespace.
    `so_peerpidfd` is a test's seam: an option number no kernel defines fails as a kernel
    without `SO_PEERPIDFD` would (TASK-0001.27).
    """
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        verdict = _verify(connection, path, jail_namespace_fd, so_peerpidfd)
    except BaseException:
        connection.close()
        raise
    if isinstance(verdict, _Verified):
        return ChannelReady(connection)
    connection.close()
    return verdict


def _verify(
    connection: socket.socket, path: str, jail_namespace_fd: int, so_peerpidfd: int
) -> _Verified | ChannelNotReady | ChannelRefused:
    """`channel_ready`'s connect and check on `connection`, which it neither keeps nor closes.
    The one raise is `OSError` reading `jail_namespace_fd`."""
    try:
        connection.connect(path)
    except OSError:
        return ChannelNotReady()
    try:
        peer_pid, _uid, _gid = struct.unpack(
            "3i",
            connection.getsockopt(
                socket.SOL_SOCKET,
                getattr(socket, "SO_PEERCRED", 17),
                12,
            ),
        )
    except OSError:
        return ChannelRefused(PEER_LOOKUP_FAILED)
    try:
        pidfd = connection.getsockopt(socket.SOL_SOCKET, so_peerpidfd)
    except OSError as exc:
        if exc.errno == errno.ENOPROTOOPT:
            return ChannelRefused(KERNEL_UNSUPPORTED)
        return ChannelRefused(PEER_LOOKUP_FAILED)
    try:
        peer_namespace = os.readlink(f"/proc/{peer_pid}/ns/pid")
        # The pidfd names the very process the kernel recorded; a reused pid differs.
        with open(f"/proc/self/fdinfo/{pidfd}") as handle:
            pidfd_pid = next(int(line.split()[1]) for line in handle if line.startswith("Pid:"))
    except OSError:
        return ChannelRefused(PEER_LOOKUP_FAILED)
    finally:
        os.close(pidfd)
    if pidfd_pid != peer_pid:
        return ChannelRefused(PEER_LOOKUP_FAILED)
    jail_namespace = os.readlink(f"/proc/self/fd/{jail_namespace_fd}")
    if peer_namespace != jail_namespace:
        return ChannelRefused(PEER_OUTSIDE_JAIL)
    return _Verified()


def create(path: str) -> None:
    """Make `path` and its missing parents, and set it to 0o700 even if it existed."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(stat.S_IRWXU)


def remove(path: str) -> None:
    """Remove `path` and everything in it; an `OSError` propagates."""
    shutil.rmtree(path)
