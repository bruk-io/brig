"""Processes: spawn one leading its own group, signal the group, peek at and release a pid, and
ask whether the group is alive. Plain data in and out (decision-0001 rule 1).

`peek` reads an exit status without releasing the pid (`WNOWAIT`) and `release` collects it
later, so a pid teardown still has to check cannot be reused in between (decision-0003).
"""

import errno
import fcntl
import os
import resource
import shutil
import signal
import time
from collections.abc import Mapping
from dataclasses import dataclass

_POLL_INTERVAL_S = 0.01
"""How often `group_alive_deadline` checks again: close to the deadline, without spinning."""

_FD_SCAN_CAP = 4096
"""The highest fd `_open_inheritable_fds` probes where there is no `/proc/self/fd` (macOS):
probing up to a soft `RLIMIT_NOFILE` of a million measured ~18ms a spawn, against ~1ms here.
An inheritable fd above it is not closed (TASK-0001.05)."""


def _open_inheritable_fds() -> frozenset[int]:
    """Every fd of this process that is open and inheritable now: `/proc/self/fd` where it
    exists, else a probe up to `_FD_SCAN_CAP`."""
    try:
        candidates: range | tuple[int, ...] = tuple(
            int(name) for name in os.listdir("/proc/self/fd")
        )
    except OSError:
        soft_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        candidates = range(min(soft_limit, _FD_SCAN_CAP))
    inheritable: set[int] = set()
    for fd in candidates:
        try:
            if os.get_inheritable(fd):
                inheritable.add(fd)
        except OSError:
            continue
    return frozenset(inheritable)


def _close_actions(
    inheritable_fds: tuple[int, ...], *, protect: frozenset[int] = frozenset()
) -> list[tuple[int, int]]:
    """One `POSIX_SPAWN_CLOSE` per open, inheritable fd outside `inheritable_fds` and `protect`
    (the sources the `DUP2` actions still read). `posix_spawn` has no "close all but these"."""
    allowed = set(inheritable_fds) | protect
    return [
        (os.POSIX_SPAWN_CLOSE, fd) for fd in sorted(_open_inheritable_fds()) if fd not in allowed
    ]


def _resolve_fd_sources(fds: Mapping[int, int]) -> tuple[dict[int, int], tuple[int, ...]]:
    """`fds` (child fd -> this process's fd) with every source that is also a target moved, by
    `F_DUPFD`, above every target, and the fds that opened, for the caller to close after the
    spawn.

    A `DUP2` from a fd to itself does nothing, not even clear close-on-exec, and a source sitting
    at another pair's target would be overwritten before it is read; a first `os.pipe()` lands
    on 3, which is `wire.REQUEST_FD`. `os.dup` cannot move it: it takes the lowest free fd.
    """
    targets = frozenset(fds)
    floor = max(targets) + 1
    resolved: dict[int, int] = {}
    relocated: list[int] = []
    for target, source in fds.items():
        if source in targets:
            new_source = fcntl.fcntl(source, fcntl.F_DUPFD, floor)
            relocated.append(new_source)
            resolved[target] = new_source
        else:
            resolved[target] = source
    return resolved, tuple(relocated)


def _fd_actions(resolved_fds: Mapping[int, int]) -> list[tuple[int, ...]]:
    """The file actions giving the child the fds `resolved_fds` names: every `DUP2` first, then
    a `CLOSE` of each source that is not itself a target. Empty for an empty mapping."""
    actions: list[tuple[int, ...]] = [
        (os.POSIX_SPAWN_DUP2, source, target) for target, source in resolved_fds.items()
    ]
    close_fds = set(resolved_fds.values()) - set(resolved_fds)
    actions += [(os.POSIX_SPAWN_CLOSE, fd) for fd in sorted(close_fds)]
    return actions


@dataclass(frozen=True)
class _SpawnedProcess:
    """A process `spawn` started: its pid, its group's pgid (always equal to it), and whether its
    session was detached too. `session_detached` is `False` where the interpreter has no
    `setsid` for `posix_spawn`: the controlling terminal is then shared, and the TIOCSTI hole
    is left for the jail type to close (TASK-0001.12).
    """

    pid: int
    pgid: int
    session_detached: bool


@dataclass(frozen=True)
class ProcessUnknown:
    """What `reap` and `peek` return when `pid` is no longer this process's child (`ECHILD`):
    something already released it, and its exit code is gone."""


class SpawnError(Exception):
    """Raised when `spawn` could not start `argv`.

    On Linux an `argv[0]` that vanishes between `spawn`'s pre-check and the spawn does not raise:
    glibc's `posix_spawnp` starts a child that exits 127 (TASK-0014).

    Args:
        argv: The command that could not be run.
        errno: The `OSError.errno` the OS reported for the failed spawn, or
            `errno.ENOENT` when it was `spawn`'s own pre-check that failed
            rather than the OS.
    """

    def __init__(self, argv: tuple[str, ...], *, errno: int) -> None:
        super().__init__(f"could not spawn {argv!r}: {os.strerror(errno)}")
        self.argv = argv
        self.errno = errno


def _spawn_leading_a_new_group(
    argv: tuple[str, ...],
    spawn_env: dict[str, str],
    file_actions: list[tuple[int, ...]],
) -> tuple[int, bool]:
    """Start `argv` with `posix_spawnp` leading a new group, and say whether its session was
    detached too. Tries `setsid=True`, and on `NotImplementedError` (raised before any fork)
    `setpgroup=0`.

    Asked, never inferred from the platform: uv's managed CPython is built against a glibc 2.17
    sysroot, which compiles `POSIX_SPAWN_SETSID` out whatever glibc it runs on (TASK-0001.12).
    An `OSError` propagates.
    """
    try:
        pid = os.posix_spawnp(
            argv[0], list(argv), spawn_env, file_actions=file_actions, setsid=True
        )
    except NotImplementedError:
        pass
    else:
        return pid, True
    pid = os.posix_spawnp(argv[0], list(argv), spawn_env, file_actions=file_actions, setpgroup=0)
    return pid, False


def spawn(
    argv: tuple[str, ...],
    inheritable_fds: tuple[int, ...],
    *,
    env: Mapping[str, str] | None = None,
    fds: Mapping[int, int] | None = None,
) -> _SpawnedProcess:
    """Start `argv` as the leader of a new process group, and of a new session where the
    interpreter allows (`_SpawnedProcess.session_detached`). `posix_spawnp` forks and execs in
    the C library, so no Python runs after the fork.

    Args:
        argv: The command; `argv[0]` is searched for on this process's `PATH`.
        inheritable_fds: The complete fd allow-list: every other open, inheritable fd is closed
            in the child.
        env: The child's environment; this process's when `None`.
        fds: Child fd -> this process's fd to give it there, by `DUP2` in the spawn itself.

    There is no `cwd`: `posix_spawn` has no portable action for it, and `os.chdir` around the
    call would move the embedder's own threads.

    Two measured hazards are handled. A `CLOSE` action on a fd another thread closed first fails
    the whole spawn with `EBADF` (TASK-0001.09): it is retried once with a fresh scan, and a
    second `EBADF` raises. `posix_spawnp` searches the caller's `PATH`, not `env`'s, and on
    Linux does not raise for a missing `argv[0]` (the child exits 127): `argv[0]` is resolved
    with `shutil.which` first, against the same `PATH` (TASK-0014).

    Raises:
        SpawnError: `argv[0]` does not resolve, or the spawn failed (twice, for `EBADF`); its
            `errno` says why.
    """
    spawn_env = dict(env) if env is not None else dict(os.environ)
    if shutil.which(argv[0], path=os.environ.get("PATH", os.defpath)) is None:
        raise SpawnError(argv, errno=errno.ENOENT)
    resolved_fds, relocated = _resolve_fd_sources(fds) if fds else ({}, ())
    protect = frozenset(resolved_fds.values())
    fd_actions = _fd_actions(resolved_fds)
    try:
        try:
            pid, session_detached = _spawn_leading_a_new_group(
                argv, spawn_env, _close_actions(inheritable_fds, protect=protect) + fd_actions
            )
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise SpawnError(argv, errno=exc.errno if exc.errno is not None else 0) from exc
            try:
                pid, session_detached = _spawn_leading_a_new_group(
                    argv,
                    spawn_env,
                    _close_actions(inheritable_fds, protect=protect) + fd_actions,
                )
            except OSError as retry_exc:
                raise SpawnError(
                    argv, errno=retry_exc.errno if retry_exc.errno is not None else 0
                ) from retry_exc
    finally:
        # The fds `_resolve_fd_sources` opened, once every attempt is done with them.
        for fd in relocated:
            os.close(fd)
    return _SpawnedProcess(pid=pid, pgid=pid, session_detached=session_detached)


def reap(pid: int) -> int | ProcessUnknown:
    """Wait for `pid` to exit and return its exit code (negative for a signal), or
    `ProcessUnknown` if it is no longer this process's child."""
    try:
        _, status = os.waitpid(pid, 0)
    except ChildProcessError:
        return ProcessUnknown()
    return os.waitstatus_to_exitcode(status)


def signal_group(pgid: int, sig: signal.Signals) -> None:
    """Send `sig` to every process in the group `pgid`; a no-op once it is gone. Every `OSError`
    is swallowed: macOS answers `EPERM`, not `ESRCH`, for a group of zombies (TASK-0001.08).
    """
    try:
        os.killpg(pgid, sig)
    except OSError:
        pass


def _exitcode_from_siginfo(info: os.waitid_result) -> int:
    """A `waitid` result as `waitstatus_to_exitcode` would give it: the exit code, or the
    negative signal number."""
    if info.si_code == os.CLD_EXITED:
        return info.si_status
    return -info.si_status


def peek(pid: int) -> int | None | ProcessUnknown:
    """Whether `pid` has exited, without releasing it (`WNOWAIT`) and without blocking.

    Returns:
        Its exit code once it has exited; `None` while it runs; `ProcessUnknown` once it is no
        longer this process's child.
    """
    try:
        info = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
    except ChildProcessError:
        return ProcessUnknown()
    if info is None:
        return None
    return _exitcode_from_siginfo(info)


def release(pid: int) -> None:
    """Collect `pid`'s exit status so its pid can be reused; a no-op if it has not exited or is
    no longer this process's child (decision-0003)."""
    try:
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG)
    except ChildProcessError:
        pass


def _group_alive_proc_scan(pgid: int, held: frozenset[int], proc_root: str = "/proc") -> bool:
    """Whether anything in the group `pgid` other than the pids in `held` is alive and not a
    zombie, by reading every `/proc/<pid>/stat` (Linux's `killpg(pgid, 0)` cannot tell a group
    of zombies from a live one, decision-0003). An entry that vanishes, is unreadable or is
    malformed is skipped; `stat` is split on its last `)`, since `comm` may hold one.
    `proc_root` is `/proc` except in a test.
    """
    for name in os.listdir(proc_root):
        if not name.isdigit():
            continue
        candidate = int(name)
        if candidate in held:
            continue
        try:
            with open(f"{proc_root}/{name}/stat") as handle:
                stat_line = handle.read()
        except FileNotFoundError, ProcessLookupError, PermissionError:
            continue
        _, _, rest = stat_line.rpartition(")")
        fields = rest.split()
        try:
            state, candidate_pgid = fields[0], fields[2]
            if int(candidate_pgid) == pgid and state != "Z":
                return True
        except IndexError, ValueError:
            continue
    return False


def group_alive(pgid: int, held: frozenset[int] = frozenset(), proc_root: str = "/proc") -> bool:
    """Whether anything in the group `pgid`, other than the pids in `held`, is still alive.

    With nothing held, `killpg(pgid, 0)`; any `OSError` means gone (macOS answers `EPERM` for an
    all-zombie group, TASK-0001.08). With pids held, the `/proc` scan, falling back to `killpg`
    where there is no `/proc`. `proc_root` is `/proc` except in a test.
    """
    if held:
        try:
            return _group_alive_proc_scan(pgid, held, proc_root)
        except FileNotFoundError:
            pass
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    return True


def group_alive_deadline(pid: int, pgid: int, deadline: float) -> bool:
    """Poll `group_alive` until it reports gone (`False`) or `time.monotonic()` passes `deadline`
    (`True`), peeking `pid`, the leader, before each check and leaving it out once it has
    exited: the post-KILL grace window (TASK-0001.07)."""
    while True:
        outcome = peek(pid)
        held = frozenset({pid}) if isinstance(outcome, int) else frozenset()
        if not group_alive(pgid, held):
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(_POLL_INTERVAL_S, remaining))
