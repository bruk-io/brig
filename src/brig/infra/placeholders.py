"""The directories a jail makes on the host for bwrap to mount over at absent paths, and their
removal once no jail mounts over them (TASK-0027). Plain data in and out.

bwrap creates a missing mountpoint on the writable source beneath it, and removing one while
another jail mounts over it detaches that jail's mount. So each jail records, under brig's state
directory, the paths it holds and the directories it made (each by its `(st_dev, st_ino)`), and
who holds them: the embedder process and, once it starts, the jail's bwrap, each by pid and start
time, so a recycled pid is not taken for the jail. Under one per-user lock, a jail's teardown
removes its record and every dead jail's, and removes a directory one of them made only when no
live record holds a path at or beneath it, it is still the directory that was made, and it is
empty.
"""

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_RECORDS = "placeholders"
_LOCK = "placeholders.lock"


@dataclass(frozen=True)
class _Holder:
    pid: int
    started: str


@dataclass(frozen=True)
class _Made:
    path: str
    device: int
    inode: int


@dataclass(frozen=True)
class _Record:
    embedder: _Holder | None
    jail: _Holder | None
    holds: tuple[str, ...]
    made: tuple[_Made, ...]


def _start_time(pid: int) -> str | None:
    """`pid`'s start time in clock ticks since boot (`/proc/<pid>/stat` field 22), or `None`."""
    try:
        with open(f"/proc/{pid}/stat") as handle:
            stat = handle.read()
    except OSError:
        return None
    return stat.rsplit(")", 1)[1].split()[19]


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
            "made": [[m.path, m.device, m.inode] for m in record.made],
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
            made=tuple(_Made(str(p), int(d), int(i)) for p, d, i in raw["made"]),
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
                    made.append(_Made(str(directory), info.st_dev, info.st_ino))
            record = records / f"{jail_id}.json"
            entry = _Record(_holder(os.getpid()), None, tuple(holds), tuple(made))
            record.write_text(_encode(entry))
        except OSError:
            _remove(tuple(made), held=frozenset())
            raise
        return record


def attach(record: Path, jail_pid: int) -> None:
    """Note in `record` that its jail's bwrap is `jail_pid`, which from now on says whether the
    jail is alive. An `OSError` rewriting it propagates.
    """
    entry = _read(record)
    if entry is not None:
        entry = _Record(entry.embedder, _holder(jail_pid), entry.holds, entry.made)
        record.write_text(_encode(entry))


def release(state_dir: Path, record: Path) -> None:
    """Remove `record` and every dead jail's record, and each directory one of them made that no
    live jail holds, is still the directory that was made, and is empty, deepest first. An
    `OSError` opening the lock or the records directory propagates.
    """
    with _locked(state_dir) as records:
        done: list[tuple[Path, _Record]] = []
        held: set[str] = set()
        for path in sorted(records.glob("*.json")):
            entry = _read(path)
            if entry is None:
                continue
            if path == record or not _alive(entry):
                done.append((path, entry))
            else:
                held.update(entry.holds)
        for path, entry in done:
            kept = _remove(entry.made, frozenset(held))
            if kept and path != record:
                path.write_text(_encode(_Record(entry.embedder, entry.jail, (), kept)))
            elif kept:
                # Ours, but a live jail still mounts over some of it: hand it to a record no
                # process holds, so the next release after that jail's removes it.
                (records / f"{path.stem}.left.json").write_text(
                    _encode(_Record(None, None, (), kept))
                )
                path.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
        record.unlink(missing_ok=True)


def _remove(made: tuple[_Made, ...], held: frozenset[str]) -> tuple[_Made, ...]:
    """Remove each of `made` no path in `held` is at or beneath, deepest first; return the ones
    kept because a live jail holds them. One that is gone, replaced or not empty is dropped."""
    kept: list[_Made] = []
    for dead in sorted(made, key=lambda m: -m.path.count("/")):
        if any(h == dead.path or h.startswith(dead.path + "/") for h in held):
            kept.append(dead)
            continue
        try:
            info = os.lstat(dead.path)
            if (info.st_dev, info.st_ino) == (dead.device, dead.inode):
                os.rmdir(dead.path)
        except OSError:
            continue
    return tuple(kept)
