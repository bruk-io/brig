"""Channels on the real host: the channel directory's creation, the fd held on it, and its
removal, finding and holding the jail's PID namespace, the verified connect beneath that fd that
says a channel is ready (decision-0005, TASK-0045), and signalling the jail's PID 1. Plain data
in and out (decision-0001 rule 1).
"""

import ctypes
import errno
import fcntl
import os
import shutil
import signal
import socket
import stat
import struct
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

SO_PEERPIDFD = getattr(socket, "SO_PEERPIDFD", 77)
"""`SO_PEERPIDFD` (Linux 6.5+), or its kernel ABI number where `socket` has no name for it.
Whether the kernel supports it is learned only by asking (`channel_ready`)."""

_SOL_LOCAL = 0
"""Darwin's socket option level (`SOL_LOCAL` in `<sys/un.h>`) for `AF_UNIX` peer credentials."""

_LOCAL_PEERTOKEN = 0x006
"""Darwin's `LOCAL_PEERTOKEN` (`<sys/un.h>`): 32-byte kernel `audit_token_t` carrying `euid`,
`pid`, and `pidversion` of the `listen()` caller (decision-0010 item 3)."""

_F_GETPATH = getattr(fcntl, "F_GETPATH", 50)
"""Darwin's `fcntl(2)` command returning the open file descriptor's vnode path."""

_PROC_PIDTBSDINFO = 3
_PROC_PIDUNIQIDENTIFIERINFO = 17
_SZOMB = 5


class _ProcBsdInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class _ProcUniqIdentifierInfo(ctypes.Structure):
    _fields_ = [
        ("p_uniqueid", ctypes.c_uint64),
        ("p_uuid", ctypes.c_uint8 * 16),
        ("p_puniqueid", ctypes.c_uint64),
        ("p_idversion", ctypes.c_int32),
        ("p_reserve2", ctypes.c_uint32),
        ("p_reserve3", ctypes.c_uint64),
        ("p_reserve4", ctypes.c_uint64),
    ]


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
    """Nothing there takes a connection yet: no socket at the name, or the connect failed (a
    full backlog included). Transient."""


@dataclass(frozen=True)
class ChannelRefused:
    """`channel_ready`'s refusal, `reason` one of the three names below. Terminal for this
    connection. Strings, not an `Enum`: `presentation/ports.py` holds the `Enum` an embedder
    matches on.
    """

    reason: str


PEER_OUTSIDE_JAIL = "peer_outside_jail"
"""The listener's PID namespace is not the jail's, a nested one included; or the channel's name
is a symbolic link, refused before any connect, since what it names can be anywhere."""

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


def _nspid(pid: int, proc_root: str = "/proc") -> str | None:
    """`pid`'s `NSpid` line: its pid in each PID namespace, outermost first; `None` when its
    `status` carries no `NSpid:` line (a task read mid-exit can open `status` and yield none,
    TASK-0050), which the caller reads as "this candidate is not the jail's PID 1", never "the
    scan is over". Its `OSError` is left to the caller."""
    with open(f"{proc_root}/{pid}/status") as handle:
        return next(
            (line.split(":", 1)[1].strip() for line in handle if line.startswith("NSpid:")), None
        )


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


def _darwin_bsd_info(pid: int) -> _ProcBsdInfo | None:
    """`proc_pidinfo(PROC_PIDTBSDINFO)` for `pid` on Darwin, or `None` when gone or a zombie."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    libc.proc_pidinfo.restype = ctypes.c_int
    info = _ProcBsdInfo()
    size = ctypes.sizeof(info)
    if libc.proc_pidinfo(pid, _PROC_PIDTBSDINFO, 0, ctypes.byref(info), size) != size:
        return None
    if info.pbi_status == _SZOMB:
        return None
    return info


def _darwin_idversion(pid: int) -> int | None:
    """`p_idversion` from `proc_pidinfo(PROC_PIDUNIQIDENTIFIERINFO)` for `pid` on Darwin."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    libc.proc_pidinfo.restype = ctypes.c_int
    info = _ProcUniqIdentifierInfo()
    size = ctypes.sizeof(info)
    if libc.proc_pidinfo(pid, _PROC_PIDUNIQIDENTIFIERINFO, 0, ctypes.byref(info), size) != size:
        return None
    return int(info.p_idversion)


def _darwin_children(pid: int) -> list[int]:
    """Live non-zombie child PIDs of `pid` on Darwin via `proc_listchildpids`."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.proc_listchildpids.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
    libc.proc_listchildpids.restype = ctypes.c_int
    buf = (ctypes.c_int * 256)()
    count = libc.proc_listchildpids(pid, buf, ctypes.sizeof(buf))
    if count <= 0:
        return []
    return [
        int(buf[idx])
        for idx in range(min(count, 256))
        if buf[idx] > 0 and _darwin_bsd_info(int(buf[idx])) is not None
    ]


def _darwin_jail_group_fd(supervisor_pid: int) -> int | JailPid1Exited:
    """An open fd holding `supervisor_pid`'s process group ID on Darwin, or `JailPid1Exited` when
    `supervisor_pid` has already exited or become a zombie.

    Raises:
        OSError: the temporary file holding the process group ID could not be created or written.
    """
    info = _darwin_bsd_info(supervisor_pid)
    if info is None:
        return JailPid1Exited()
    fd, path = tempfile.mkstemp(prefix="brig-ns-")
    try:
        os.unlink(path)
        with os.fdopen(fd, "w", encoding="ascii", closefd=False) as handle:
            handle.write(f"{info.pbi_pgid}\n")
    except OSError:
        os.close(fd)
        raise
    return fd


def jail_pid1_namespace(
    bwrap_pid: int,
    deadline: float,
    proc_root: str = "/proc",
) -> int | JailPid1NotFound | JailPid1Exited:
    """An open fd on the jail's PID namespace (or process-group identity fd on Darwin), found as
    the child of `bwrap_pid` whose `NSpid` ends in 1; `JailPid1NotFound` once `deadline` passes,
    `JailPid1Exited` as soon as `bwrap_pid` is gone with no PID 1 found.

    `bwrap_pid` is the outer bwrap on Linux, whose own namespace is the host's (measured,
    TASK-0001.24): comparing peers against it would pass every peer. The fd is held, never read,
    so the namespace's inode cannot be recycled (decision-0005 item 1). On Darwin when `proc_root`
    is the host's `/proc` (absent), `bwrap_pid` is the Seatbelt supervisor process (`sandbox-exec`
    execs in place) and the returned fd holds its process group ID (decision-0010 item 3).
    """
    if sys.platform == "darwin" and proc_root == "/proc" and not Path(proc_root).exists():
        return _darwin_jail_group_fd(bwrap_pid)
    while True:
        for child in _children(bwrap_pid, proc_root):
            try:
                nspid = _nspid(child, proc_root)
                if nspid is None or nspid.split()[-1:] != ["1"]:
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


def _signal_darwin_supervisor(supervisor_pid: int, sig: int, timeout_s: float) -> bool:
    """Send `sig` to `supervisor_pid` on Darwin once it has spawned a child, verifying its
    `p_idversion` before and after to guard against PID reuse."""
    deadline = time.monotonic() + timeout_s
    while True:
        info = _darwin_bsd_info(supervisor_pid)
        version_before = _darwin_idversion(supervisor_pid)
        if info is None or version_before is None:
            return False
        if _darwin_children(supervisor_pid):
            if _darwin_idversion(supervisor_pid) != version_before:
                return False
            try:
                os.kill(supervisor_pid, sig)
                return True
            except OSError:
                return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL_S)


def signal_jail_pid1(
    bwrap_pid: int,
    sig: int,
    proc_root: str = "/proc",
    timeout_s: float = _SIGNAL_WAIT_S,
) -> bool:
    """Send `sig` to the jail's PID 1 (its supervisor) once it has started the command, and say
    whether it was sent.

    Waits up to `timeout_s` while the jail is still coming up (no PID 1 yet, or a PID 1 with no
    child yet): a jail `create_bwrap_jail` or `create_seatbelt_jail` just returned may not have
    started its command. `False` once the jail is gone, its PID 1 a zombie, or a PID 1 that
    started its command has none left: the command has finished.

    Through a pidfd on Linux (or `p_idversion` verification on Darwin), so a pid recycled between
    the scan and the signal is never signalled.
    """
    if sys.platform == "darwin" and proc_root == "/proc" and not Path(proc_root).exists():
        return _signal_darwin_supervisor(bwrap_pid, sig, timeout_s)
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
    pidfd_open = getattr(os, "pidfd_open", None)
    pidfd_send = getattr(signal, "pidfd_send_signal", None)
    if pidfd_open is None or pidfd_send is None:
        return False
    try:
        pidfd: int = pidfd_open(child)
    except OSError:
        return False
    try:
        again = _pid1_under(bwrap_pid, proc_root)
        if again is None or again[0] != child:
            return False
        pidfd_send(pidfd, sig)
        return True
    except OSError:
        return False
    finally:
        os.close(pidfd)


def _darwin_channel_ready(
    directory_fd: int,
    name: str,
    jail_namespace_fd: int,
    so_peerpidfd: int,
) -> ChannelReady | ChannelNotReady | ChannelRefused:
    """Darwin implementation of `channel_ready` (decision-0010 item 3)."""
    try:
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return ChannelNotReady()
    if stat.S_ISLNK(before.st_mode):
        return ChannelRefused(PEER_OUTSIDE_JAIL)
    if not stat.S_ISSOCK(before.st_mode):
        return ChannelNotReady()
    try:
        raw_dir = fcntl.fcntl(directory_fd, _F_GETPATH, bytes(1024))
        dir_path = raw_dir.split(b"\x00", 1)[0].decode("utf-8")
    except OSError, UnicodeDecodeError:
        return ChannelNotReady()
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        verdict = _verify_darwin(
            connection,
            directory_fd,
            name,
            (before.st_dev, before.st_ino),
            f"{dir_path}/{name}",
            jail_namespace_fd,
            so_peerpidfd,
        )
        if isinstance(verdict, _Verified):
            connection.setblocking(True)
    except BaseException:
        connection.close()
        raise
    if isinstance(verdict, _Verified):
        return ChannelReady(connection)
    connection.close()
    return verdict


def _verify_darwin(
    connection: socket.socket,
    directory_fd: int,
    name: str,
    expected_inode: tuple[int, int],
    target: str,
    jail_namespace_fd: int,
    so_peerpidfd: int,
) -> _Verified | ChannelNotReady | ChannelRefused:
    """Connect non-blocking to `target` on Darwin, re-verify the socket inode beneath
    `directory_fd`, and check the listener's kernel `LOCAL_PEERTOKEN` (`euid`, `pid`,
    `pidversion`) and `pbi_pgid` against `jail_namespace_fd`."""
    connection.setblocking(False)
    try:
        connection.connect(target)
    except OSError:
        return ChannelNotReady()
    try:
        after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return ChannelNotReady()
    if not stat.S_ISSOCK(after.st_mode) or (after.st_dev, after.st_ino) != expected_inode:
        return ChannelNotReady()
    option = _LOCAL_PEERTOKEN if so_peerpidfd == SO_PEERPIDFD else so_peerpidfd
    try:
        raw_token = connection.getsockopt(_SOL_LOCAL, option, 32)
    except OSError as exc:
        if exc.errno == errno.ENOPROTOOPT:
            return ChannelRefused(KERNEL_UNSUPPORTED)
        return ChannelRefused(PEER_LOOKUP_FAILED)
    if len(raw_token) != 32:
        return ChannelRefused(PEER_LOOKUP_FAILED)
    _auid, euid, _egid, _ruid, _rgid, peer_pid, _asid, peer_pidversion = struct.unpack(
        "8I", raw_token
    )
    if peer_pid <= 0:
        return ChannelRefused(PEER_LOOKUP_FAILED)
    bsd_info = _darwin_bsd_info(peer_pid)
    idversion = _darwin_idversion(peer_pid)
    if bsd_info is None or idversion is None or idversion != peer_pidversion:
        return ChannelRefused(PEER_LOOKUP_FAILED)
    if euid != os.geteuid():
        return ChannelRefused(PEER_OUTSIDE_JAIL)
    jail_pgid = os.pread(jail_namespace_fd, 64, 0).decode("ascii", errors="replace").strip()
    if str(bsd_info.pbi_pgid) != jail_pgid:
        return ChannelRefused(PEER_OUTSIDE_JAIL)
    return _Verified()


def channel_ready(
    directory_fd: int,
    name: str,
    jail_namespace_fd: int,
    *,
    so_peerpidfd: int = SO_PEERPIDFD,
    proc_root: str = "/proc",
) -> ChannelReady | ChannelNotReady | ChannelRefused:
    """Connect once to the socket `name` names directly beneath the directory `directory_fd`
    holds, and verify that the process that called `listen()` on the socket that answered is in
    the PID namespace (or Darwin jail process group) `jail_namespace_fd` names (decision-0005,
    decision-0010).

    The name is opened beneath the held directory with `O_PATH | O_NOFOLLOW` on Linux (or statted
    beneath `directory_fd` with `follow_symlinks=False` and `fcntl(F_GETPATH)` on Darwin), so the
    lookup follows no link and no path the jail can change on the way (TASK-0045). What it opens
    must be a socket: a symbolic link is `PEER_OUTSIDE_JAIL` without any connect, since a link can
    name a socket anywhere the embedder can reach and dialling it would reach that socket as
    the embedder; anything else (a file, a directory, nothing at all) is `ChannelNotReady`. The
    connect goes to that very inode without blocking: a listener whose backlog is full is
    `ChannelNotReady` at once, so the caller's deadline holds however the jail listens.

    `ChannelReady` carries the verified connection, open and set back to blocking, and its
    receiver owns it: readiness is a property of that one connection, and a later dial of the
    path follows whatever the jail has put there since, a symbolic link to a host socket
    included (TASK-0001.34). Every other outcome, and the one raise, closes the connection
    first, so only a ready attempt leaves a socket open. Like every socket Python makes, the
    connection is not inherited by a process spawned later.

    Every outcome is returned. The one raise, `OSError` for a `jail_namespace_fd` that is not
    open, comes from reading it, which is done last, so the refusals above it need no namespace.
    """
    if sys.platform == "darwin":
        return _darwin_channel_ready(directory_fd, name, jail_namespace_fd, so_peerpidfd)
    o_path = getattr(os, "O_PATH", os.O_RDONLY)
    try:
        target = os.open(name, o_path | os.O_NOFOLLOW, dir_fd=directory_fd)
    except OSError:
        return ChannelNotReady()
    try:
        kind = os.fstat(target).st_mode
        if stat.S_ISLNK(kind):
            return ChannelRefused(PEER_OUTSIDE_JAIL)
        if not stat.S_ISSOCK(kind):
            return ChannelNotReady()
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            verdict = _verify(
                connection, f"/proc/self/fd/{target}", jail_namespace_fd, so_peerpidfd, proc_root
            )
            if isinstance(verdict, _Verified):
                connection.setblocking(True)
        except BaseException:
            connection.close()
            raise
    finally:
        os.close(target)
    if isinstance(verdict, _Verified):
        return ChannelReady(connection)
    connection.close()
    return verdict


def _verify(
    connection: socket.socket,
    target: str,
    jail_namespace_fd: int,
    so_peerpidfd: int,
    proc_root: str,
) -> _Verified | ChannelNotReady | ChannelRefused:
    """`channel_ready`'s connect to `target` and check on `connection`, which it neither keeps
    nor closes. The connect is non-blocking: any `OSError` from it, `EAGAIN` from a full backlog
    included, is `ChannelNotReady`. A pidfd `fdinfo` with no `Pid:` line is `PEER_LOOKUP_FAILED`.
    The one raise is `OSError` reading `jail_namespace_fd`."""
    connection.setblocking(False)
    try:
        connection.connect(target)
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
        peer_namespace = os.readlink(f"{proc_root}/{peer_pid}/ns/pid")
        # The pidfd names the very process the kernel recorded; a reused pid differs.
        with open(f"{proc_root}/self/fdinfo/{pidfd}") as handle:
            pidfd_pid = next(
                (int(line.split()[1]) for line in handle if line.startswith("Pid:")), None
            )
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


def open_directory(path: str) -> int:
    """An `O_PATH` fd on the directory `path` (or `O_RDONLY` on Darwin), opened through no link at
    its last component, for `channel_ready` to open each channel's name beneath (TASK-0045). The
    caller owns it and closes it; like every fd Python opens, it is not inherited. An `OSError`
    propagates."""
    o_path = getattr(os, "O_PATH", os.O_RDONLY)
    return os.open(path, o_path | os.O_DIRECTORY | os.O_NOFOLLOW)


def remove(path: str) -> None:
    """Remove `path` and everything in it; an `OSError` propagates."""
    shutil.rmtree(path)
