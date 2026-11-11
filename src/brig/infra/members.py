"""A Seatbelt jail's members on Darwin: every process that carries the jail's profile, found
by what the profile decides, and killed until none is left (decision-0010 item 2, TASK-0061).

Darwin has no PID namespace. A jailed process can leave the process group teardown kills
(`posix_spawn` with `setpgroup` or `setsid`, measured), and once its parent exits it is
launchd's child, so neither the group nor the process tree finds it. What it cannot shed is its
sandbox: every process the jail starts carries the profile, and `sandbox_check` (a libSystem
export no SDK header declares, so private interface Apple may change) asks the kernel what a
given process's profile decides. Each jail's profile allows `file-read-metadata`
on its own `mark` and nothing allows it on the `decoy` beside it (brig's state directory is
masked), so a process of this user's that is sandboxed, allowed the mark and refused the decoy
is that jail's: another jail refuses the mark, an unsandboxed process is not sandboxed, and a
broader sandbox that reads the state directory allows the decoy too. Both files must exist when
asked: `sandbox_check` refuses a path that does not.
"""

import ctypes
import os
import platform
import signal
import stat
import sys
import time
from dataclasses import dataclass

_PROC_ALL_PIDS = 1
_PROC_PIDTBSDINFO = 3
_SZOMB = 5
_SANDBOX_FILTER_PATH = 1
_SANDBOX_CHECK_NO_REPORT = 0x40000000
_POLL_INTERVAL_S = 0.01
_PADDING = 5 if platform.machine() == "arm64" else 0
"""Unused fixed arguments before `sandbox_check`'s variadic one (`_libsystem`)."""
_PADS = (0,) * _PADDING


class _BsdInfo(ctypes.Structure):
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


def _libsystem() -> ctypes.CDLL:
    """libSystem, with `sandbox_check` declared so its one variadic argument reaches the stack.

    On arm64 Darwin a variadic argument is passed on the stack, where ctypes, which passes
    every argument as fixed, would put it in a register. Five unused fixed arguments fill the
    registers the named three leave, so the path lands in the first stack slot, where
    `sandbox_check` reads it (measured: without them every path check answered "refused", an
    unsandboxed process included). On x86_64 a variadic argument travels in the next register
    like a fixed one, so there the path follows the named three directly (not measured: this
    Mac is arm64).
    """
    lib = ctypes.CDLL("/usr/lib/libSystem.dylib")
    padding = [ctypes.c_long] * _PADDING
    lib.sandbox_check.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, *padding]
    lib.sandbox_check.argtypes += [ctypes.c_char_p]
    lib.sandbox_check.restype = ctypes.c_int
    lib.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
    lib.proc_listpids.restype = ctypes.c_int
    lib.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    lib.proc_pidinfo.restype = ctypes.c_int
    return lib


def _all_pids(lib: ctypes.CDLL) -> list[int]:
    """Every pid on the host now, from `proc_listpids(PROC_ALL_PIDS)`."""
    capacity = 4096
    while True:
        buffer = (ctypes.c_int * capacity)()
        used = lib.proc_listpids(_PROC_ALL_PIDS, 0, buffer, ctypes.sizeof(buffer))
        count = used // ctypes.sizeof(ctypes.c_int)
        if count < capacity:
            return [pid for pid in buffer[:count] if pid > 0]
        capacity *= 2


_SSTOP = 4
_CTL_KERN = 1
_KERN_PROCARGS2 = 49

FREEZER_MARKER = "brig-teardown-freezer"
"""The argument a jail's teardown freezer carries (`supervisor.program`), by which `freeze_and_kill`
picks it out among the jail's members. The command can forge it; a forged freezer can keep the
jail from freezing (a teardown that fails), never make a frozen jail look frozen."""


@dataclass(frozen=True)
class _Member:
    """One process of the jail, as one scan saw it."""

    pid: int
    stopped: bool
    freezer: bool


def _info(lib: ctypes.CDLL, pid: int) -> _BsdInfo | None:
    """`proc_pidinfo(PROC_PIDTBSDINFO)` for `pid`, or `None` once it is gone."""
    info = _BsdInfo()
    size = ctypes.sizeof(info)
    if lib.proc_pidinfo(pid, _PROC_PIDTBSDINFO, 0, ctypes.byref(info), size) != size:
        return None
    return info


def _decides(lib: ctypes.CDLL, pid: int, path: bytes) -> int:
    """What `pid`'s sandbox decides for `file-read-metadata` on `path`: 0 allowed, 1 refused
    (also for a process that is gone, and for a path that does not exist; measured), -1 on an
    error."""
    flags = _SANDBOX_FILTER_PATH | _SANDBOX_CHECK_NO_REPORT
    return int(lib.sandbox_check(pid, b"file-read-metadata", flags, *_PADS, path))


def profile_decision(pid: int, path: str) -> int:
    """What `pid`'s sandbox decides for `file-read-metadata` on `path`, as `sandbox_check`
    answers it: 0 allowed, 1 refused. A process that is gone reads 1, as one refused does, so a
    process that exits mid-scan reads as no member, which is why a scan checks that each one it
    asked about is still there afterwards (`_scan`). Darwin only."""
    return _decides(_libsystem(), pid, os.fsencode(path))


def _is_member(lib: ctypes.CDLL, pid: int, mark: bytes, decoy: bytes) -> bool:
    if lib.sandbox_check(pid, None, 0, *_PADS, None) != 1:
        return False
    return _decides(lib, pid, mark) == 0 and _decides(lib, pid, decoy) == 1


def _is_freezer(pid: int) -> bool:
    """Whether `pid`'s arguments (`KERN_PROCARGS2`) carry `FREEZER_MARKER`."""
    lib = ctypes.CDLL(None)
    mib = (ctypes.c_int * 3)(_CTL_KERN, _KERN_PROCARGS2, pid)
    size = ctypes.c_size_t(65536)
    buffer = ctypes.create_string_buffer(size.value)
    if lib.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
        return False
    return FREEZER_MARKER.encode() in buffer.raw[: size.value]


def _scan(mark: str, decoy: str) -> tuple[tuple[_Member, ...], bool]:
    """Every live process of this user's whose sandbox allows `mark` and refuses `decoy` (the
    jail's whose profile names `mark`), and whether the scan can be trusted: not when a process
    of this user's that it listed was gone before it had been judged. `sandbox_check` reads a gone
    process as refused, so a process that forks and exits faster than a scan (about 3 ms for
    1,000 processes) would otherwise slip through every one; its chain always has a live
    member, and a member that exits mid-scan makes the scan inconclusive instead."""
    lib = _libsystem()
    own, uid = os.getpid(), os.getuid()
    raw_mark, raw_decoy = os.fsencode(mark), os.fsencode(decoy)
    found: list[_Member] = []
    conclusive = True
    for pid in _all_pids(lib):
        if pid == own:
            continue
        before = _info(lib, pid)
        if before is None or before.pbi_uid != uid or before.pbi_status == _SZOMB:
            continue
        member = _is_member(lib, pid, raw_mark, raw_decoy)
        after = _info(lib, pid)
        if after is None or after.pbi_status == _SZOMB:
            conclusive = False
            continue
        if member:
            found.append(_Member(pid, after.pbi_status == _SSTOP, _is_freezer(pid)))
    return tuple(found), conclusive


def _intact(mark: str, decoy: str) -> bool:
    """Whether `mark` and `decoy` are both still regular files, looked up through no link.

    `sandbox_check` answers "refused" for a path that does not exist (measured), so with the
    decoy gone every sandboxed process that may read the mark (one under `(allow default)`, a
    tool's own sandbox) would pass as the jail's and be killed. Nothing tells the jail apart
    without both, so no scan is acted on unless both are there before and after it."""
    for path in (mark, decoy):
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):
                return False
        except OSError:
            return False
    return True


def is_member(mark: str, decoy: str, pid: int) -> bool:
    """Whether the live process `pid` carries the profile that names `mark`: the canary that
    `sandbox_check` answers as measured on this host, asked of a process known to be the
    jail's. Always `False` off Darwin, and while the mark or decoy is not intact (`_intact`)."""
    if sys.platform != "darwin" or not _intact(mark, decoy):
        return False
    lib = _libsystem()
    found = _is_member(lib, pid, os.fsencode(mark), os.fsencode(decoy))
    return found and _intact(mark, decoy)


def _signal(pid: int, sig: signal.Signals) -> None:
    try:
        os.kill(pid, sig)
    except OSError:
        pass


def freeze_and_kill(mark: str, decoy: str, deadline: float) -> bool:
    """End every process that carries the profile naming `mark` (decision-0010 item 2), and say
    whether none is left (`True`) before `time.monotonic()` passes `deadline` (`False`).

    A process that forks and exits in a loop outruns any scan from the host, so the jail is
    frozen from inside first: its freezer (`FREEZER_MARKER`), told with `SIGUSR1`, calls
    `kill(-1, SIGSTOP)`, which Seatbelt's `(target same-sandbox)` confines to the jail and
    which stops the freezer itself too. One pass can miss a child forked while it runs (measured:
    1 run in 15 against a fork loop), so while a scan finds a member still running, the freezer
    is continued (`SIGCONT`) and passes again. A stopped process cannot fork, so once two scans
    in a row find the same members, every one stopped, the jail is frozen, and each is killed.

    `False` at once, signalling nothing, whenever the mark or decoy is not intact before or
    after a scan (`_intact`): without both, the jail's processes cannot be told from any other
    sandboxed process of the user's.

    With no freezer left (the command killed it), each member a scan finds is killed on sight,
    with its process group: that ends a jail that does not fork in a loop, and races one that
    does, which then outlives the deadline, a failure the caller reports.
    """
    if sys.platform != "darwin":
        return True
    told: set[int] = set()
    frozen: frozenset[int] | None = None
    while True:
        if not _intact(mark, decoy):
            return False
        scan, conclusive = _scan(mark, decoy)
        if not _intact(mark, decoy):
            return False
        if conclusive and not scan:
            return True
        if time.monotonic() >= deadline:
            return False
        if conclusive and all(member.stopped for member in scan):
            pids = frozenset(member.pid for member in scan)
            if frozen == pids:
                for member in scan:
                    _signal(member.pid, signal.SIGKILL)
                frozen = None
                continue
            frozen = pids
            continue
        frozen = None
        freezers = [member for member in scan if member.freezer]
        for freezer in freezers:
            if freezer.pid not in told:
                _signal(freezer.pid, signal.SIGUSR1)
                told.add(freezer.pid)
            elif freezer.stopped:
                _signal(freezer.pid, signal.SIGCONT)
        if not freezers:
            for member in scan:
                _signal(member.pid, signal.SIGKILL)
                try:
                    os.killpg(os.getpgid(member.pid), signal.SIGKILL)
                except OSError:
                    pass
        time.sleep(_POLL_INTERVAL_S)


def reap_kept(state_dir: str, deadline: float) -> None:
    """Sweep the marks a failed teardown kept (decision-0010 item 2): each `*.mark` in
    `state_dir` whose jail's supervisor script is gone, which only a teardown that could not
    end every member leaves. Each is swept again (`freeze_and_kill`), and its mark and decoy
    removed once none is left; a mark still carried stays for the next sweep. A mark whose decoy
    is gone, or either not a regular file, is never swept and is left where it is: nothing can
    tell its jail's processes from any other sandboxed one of the user's, and removing it would
    drop the one record that a survivor may exist. Every `OSError` is swallowed: this is
    housekeeping, run before a jail is made or destroyed."""
    try:
        marks = [name for name in os.listdir(state_dir) if name.endswith(".mark")]
    except OSError:
        return
    for name in marks:
        mark = os.path.join(state_dir, name)
        stem = mark[: -len(".mark")]
        if os.path.exists(stem + ".py") or not _intact(mark, stem + ".decoy"):
            continue
        if freeze_and_kill(mark, stem + ".decoy", deadline):
            for made in (mark, stem + ".decoy"):
                try:
                    os.unlink(made)
                except OSError:
                    pass
