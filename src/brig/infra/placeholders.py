"""The directories a jail makes on the host for bwrap to mount over at absent paths, and their
removal once no jail mounts over them (TASK-0027). Plain data in and out.

bwrap creates a missing mountpoint on the writable source beneath it, and removing one while
another jail mounts over it detaches that jail's mount. So each jail records, under brig's state
directory, the paths it holds and the directories it made (each by its `(st_dev, st_ino)` and
an extended attribute brig sets on it, since a recreated directory can reuse the inode), and
who holds them: the embedder process and, once it starts, the jail's bwrap, each by pid and start
time, so a recycled pid is not taken for the jail. Under one per-user lock, a jail's teardown
removes its record and every dead jail's, and removes a directory one of them made only when no
live record holds a path at or beneath it, it is still the directory that was made, and it is
empty. It sweeps them all together, deepest first, so what is removed does not depend on the order
the records are read in, and keeps in a record each it could not remove yet, for a later sweep.
"""

import ctypes
import errno
import fcntl
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_RECORDS = "placeholders"
_LOCK = "placeholders.lock"

_XATTR_NOFOLLOW = 0x0001
_ENOATTR = getattr(errno, "ENOATTR", 93)
_PROC_PIDTBSDINFO = 3
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


@dataclass(frozen=True)
class _Holder:
    pid: int
    started: str


@dataclass(frozen=True)
class _Made:
    path: str
    device: int
    inode: int
    marked: bool


@dataclass(frozen=True)
class _Record:
    embedder: _Holder | None
    jail: _Holder | None
    holds: tuple[str, ...]
    made: tuple[_Made, ...]


_MARK = "user.brig.placeholder"
"""The extended attribute brig sets on a placeholder it made, naming the record that made it: what
tells brig's directory from one the embedder made in its place, which may have the same inode."""


def _darwin_start_time(pid: int) -> str | None:
    """`pid`'s start time (`tv_sec:tv_usec`) from `proc_pidinfo(PROC_PIDTBSDINFO)` on Darwin, or
    `None` when `pid` is gone or a zombie (`SZOMB`)."""
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
    return f"{info.pbi_start_tvsec}:{info.pbi_start_tvusec}"


def _start_time(pid: int) -> str | None:
    """`pid`'s start time in clock ticks since boot (`/proc/<pid>/stat` field 22 on Linux, or
    `proc_pidinfo` on Darwin), or `None` once it has exited: a zombie (state Z / SZOMB) or a dead
    process (X) holds no mount, so it counts as gone."""
    try:
        with open(f"/proc/{pid}/stat") as handle:
            stat = handle.read()
    except OSError:
        if sys.platform == "darwin":
            return _darwin_start_time(pid)
        return None
    fields = stat.rsplit(")", 1)[1].split()
    return None if fields[0] in {"Z", "X"} else fields[19]


def _setxattr_nofollow(path: str, name: str, value: bytes) -> None:
    """Set extended attribute `name` on `path` without following symlinks.

    Raises:
        OSError: the extended attribute could not be set.
    """
    std_setxattr = getattr(os, "setxattr", None)
    if std_setxattr is not None:
        std_setxattr(path, name, value, follow_symlinks=False)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    libc.setxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    libc.setxattr.restype = ctypes.c_int
    rc = libc.setxattr(
        os.fsencode(path),
        name.encode(),
        value,
        len(value),
        0,
        _XATTR_NOFOLLOW,
    )
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), path)


def _getxattr_nofollow(path: str, name: str) -> bytes:
    """Read extended attribute `name` on `path` without following symlinks.

    Raises:
        OSError: the extended attribute could not be read.
    """
    std_getxattr = getattr(os, "getxattr", None)
    if std_getxattr is not None:
        raw: bytes = std_getxattr(path, name, follow_symlinks=False)
        return raw
    libc = ctypes.CDLL(None, use_errno=True)
    libc.getxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    libc.getxattr.restype = ctypes.c_ssize_t
    buf = ctypes.create_string_buffer(256)
    rc = libc.getxattr(
        os.fsencode(path),
        name.encode(),
        buf,
        ctypes.sizeof(buf),
        0,
        _XATTR_NOFOLLOW,
    )
    if rc < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), path)
    return buf.raw[:rc]


def _marked(directory: Path, jail_id: str) -> bool:
    """Mark `directory` as brig's (`_MARK`) and say whether that worked: a filesystem without user
    extended attributes leaves it to the inode alone, which the record says."""
    try:
        _setxattr_nofollow(str(directory), _MARK, jail_id.encode())
    except OSError:
        return False
    return True


def _write(path: Path, record: _Record) -> None:
    """Replace `path` with `record` whole: a reader sees the old record or the new, never half."""
    partial = path.with_name(path.name + ".partial")
    partial.write_text(_encode(record))
    os.replace(partial, path)


def _holder(pid: int) -> _Holder | None:
    started = _start_time(pid)
    return None if started is None else _Holder(pid, started)


def _alive(record: _Record) -> bool:
    """A record's jail is alive while its bwrap runs, or, before it has one, while its embedder
    does: each the same process it was (same pid, same start time)."""
    holder = record.jail if record.jail is not None else record.embedder
    return holder is not None and _start_time(holder.pid) == holder.started


def _encode(record: _Record) -> str:
    def holder(h: _Holder | None) -> list[object] | None:
        return None if h is None else [h.pid, h.started]

    return json.dumps(
        {
            "embedder": holder(record.embedder),
            "jail": holder(record.jail),
            "holds": list(record.holds),
            "made": [[m.path, m.device, m.inode, m.marked] for m in record.made],
        }
    )


def _decode(text: str) -> _Record | None:
    try:
        raw = json.loads(text)
        holders = [
            None if raw[key] is None else _Holder(int(raw[key][0]), str(raw[key][1]))
            for key in ("embedder", "jail")
        ]
        return _Record(
            embedder=holders[0],
            jail=holders[1],
            holds=tuple(str(path) for path in raw["holds"]),
            made=tuple(_Made(str(p), int(d), int(i), bool(m)) for p, d, i, m in raw["made"]),
        )
    except ValueError, KeyError, TypeError, IndexError:
        return None


def _read(path: Path) -> _Record | None:
    try:
        return _decode(path.read_text())
    except OSError:
        return None


@contextmanager
def _locked(state_dir: Path) -> Iterator[Path]:
    records = state_dir / _RECORDS
    records.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(state_dir / _LOCK, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield records
    finally:
        os.close(fd)


def hold(state_dir: Path, jail_id: str, paths: tuple[str, ...]) -> Path:
    """Make every directory missing on the way to each of `paths` (each path included) and
    record them as this jail's; record that this jail holds each of `paths` that it made or that
    another jail's record says that jail made (a placeholder another jail still mounts over, which
    this one will mount over too); return the record's path. A path already there that no record
    made is the embedder's, and is neither held nor ever removed.

    Raises:
        OSError: a directory could not be made or the record written; whatever this call made is
            removed again first.
    """
    with _locked(state_dir) as records:
        others = {
            made.path
            for other in records.glob("*.json")
            if (entry := _read(other)) is not None
            for made in entry.made
        }
        made: list[_Made] = []
        holds: list[str] = []
        try:
            for path in paths:
                if Path(path).exists() or Path(path).is_symlink():
                    if path in others:
                        holds.append(path)
                    continue
                holds.append(path)
                missing: list[Path] = []
                current = Path(path)
                while not current.exists() and not current.is_symlink():
                    missing.append(current)
                    current = current.parent
                for directory in reversed(missing):
                    directory.mkdir(mode=0o755)
                    info = directory.lstat()
                    made.append(
                        _Made(str(directory), info.st_dev, info.st_ino, _marked(directory, jail_id))
                    )
            record = records / f"{jail_id}.json"
            entry = _Record(_holder(os.getpid()), None, tuple(holds), tuple(made))
            _write(record, entry)
        except OSError:
            _remove(tuple(made), held=frozenset())
            raise
        return record


def attach(state_dir: Path, record: Path, jail_pid: int) -> None:
    """Note in `record` that its jail's bwrap is `jail_pid`, which from now on says whether the
    jail is alive; under the lock, replaced whole. An `OSError` rewriting it propagates.
    """
    with _locked(state_dir):
        entry = _read(record)
        if entry is not None:
            _write(record, _Record(entry.embedder, _holder(jail_pid), entry.holds, entry.made))


def release(state_dir: Path, record: Path) -> None:
    """Remove `record` and every dead jail's record, and each directory one of them made that no
    live jail holds, is still the directory that was made, and is empty: all of them together,
    deepest first, so a directory one record made inside another's goes before it whichever record
    is read first. One that cannot be removed for a reason other than being gone or replaced (not
    empty yet, say) stays in a record no process holds, so a later release tries it again. An
    `OSError` opening the lock or the records directory, or writing that record, propagates.
    """
    with _locked(state_dir) as records:
        done: list[Path] = []
        made: list[_Made] = []
        held: set[str] = set()
        for path in sorted(records.glob("*.json")):
            entry = _read(path)
            if entry is None:
                continue
            if path == record or not _alive(entry):
                done.append(path)
                made.extend(entry.made)
            else:
                held.update(entry.holds)
        kept = _remove(tuple(made), frozenset(held))
        left = records / f"{record.stem}.left.json"
        if kept:
            # Written before the records it replaces go, so a crash between loses none of them.
            _write(left, _Record(None, None, (), kept))
        for path in done:
            if not (kept and path == left):
                path.unlink(missing_ok=True)
        record.unlink(missing_ok=True)


def _remove(made: tuple[_Made, ...], held: frozenset[str]) -> tuple[_Made, ...]:
    """Remove each of `made` no path in `held` is at or beneath, deepest first; return the ones
    kept: those a live jail holds, and those that could not be removed for a reason other than
    being gone or replaced. One that is gone or replaced is dropped."""
    return tuple(
        dead
        for dead in sorted(made, key=lambda m: -m.path.count("/"))
        if any(h == dead.path or h.startswith(dead.path + "/") for h in held) or not _gone(dead)
    )


def _gone(made: _Made) -> bool:
    """Remove `made` if it is still the directory brig made, and say whether it is gone now:
    removed, already gone, or replaced by an entry brig did not make (another inode, or brig's
    mark missing). `False` when it is still brig's but could not be removed or checked."""
    try:
        info = os.lstat(made.path)
        if (info.st_dev, info.st_ino) != (made.device, made.inode):
            return True
        if made.marked and not _has_mark(made.path):
            return True
        os.rmdir(made.path)
    except FileNotFoundError, NotADirectoryError:
        return True
    except OSError:
        return False
    return True


def _has_mark(path: str) -> bool:
    """Whether `path` carries brig's mark (`_MARK`).

    Raises:
        OSError: the attribute could not be read for a reason other than its absence.
    """
    try:
        return bool(_getxattr_nofollow(path, _MARK))
    except OSError as error:
        if error.errno in {errno.ENODATA, errno.ENOTSUP, _ENOATTR}:
            return False
        raise
