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
import sys
import time

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


def _live_and_mine(lib: ctypes.CDLL, pid: int) -> bool:
    """Whether `pid` is a live process (no zombie) of this process's real user."""
    info = _BsdInfo()
    size = ctypes.sizeof(info)
    if lib.proc_pidinfo(pid, _PROC_PIDTBSDINFO, 0, ctypes.byref(info), size) != size:
        return False
    return bool(info.pbi_status != _SZOMB and info.pbi_uid == os.getuid())


def _decides(lib: ctypes.CDLL, pid: int, path: bytes) -> int:
    """What `pid`'s sandbox decides for `file-read-metadata` on `path`: 0 allowed, 1 refused,
    -1 unknown (the process is gone)."""
    flags = _SANDBOX_FILTER_PATH | _SANDBOX_CHECK_NO_REPORT
    return int(lib.sandbox_check(pid, b"file-read-metadata", flags, *_PADS, path))


def _is_member(lib: ctypes.CDLL, pid: int, mark: bytes, decoy: bytes) -> bool:
    if lib.sandbox_check(pid, None, 0, *_PADS, None) != 1:
        return False
    return _decides(lib, pid, mark) == 0 and _decides(lib, pid, decoy) == 1


def _members_of(mark: str, decoy: str) -> tuple[int, ...]:
    """Every live process of this user's whose sandbox allows `mark` and refuses `decoy`: the
    jail's whose profile names `mark`. Empty off Darwin, which has no `sandbox_check`."""
    if sys.platform != "darwin":
        return ()
    lib = _libsystem()
    own = os.getpid()
    raw_mark, raw_decoy = os.fsencode(mark), os.fsencode(decoy)
    return tuple(
        pid
        for pid in _all_pids(lib)
        if pid != own and _live_and_mine(lib, pid) and _is_member(lib, pid, raw_mark, raw_decoy)
    )


def kill_members(mark: str, decoy: str, deadline: float) -> bool:
    """`SIGKILL` every member (`_members_of`) and look again, until a look finds none (`True`) or
    `time.monotonic()` passes `deadline` (`False`). A member forked while the last one was being
    killed is found by the next look. A pid that exited and was reused between a look and its
    kill could be signalled; the look and the kill are microseconds apart, and Darwin hands
    pids out in rising order."""
    while True:
        found = _members_of(mark, decoy)
        if not found:
            return True
        for pid in found:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        if time.monotonic() >= deadline:
            return not _members_of(mark, decoy)
        time.sleep(_POLL_INTERVAL_S)
