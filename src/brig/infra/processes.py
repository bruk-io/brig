"""Processes: spawn one, signal its group, reap it, read whether a pid is alive.

Plain data in, plain data out (decision-0001 rule 1): every function here takes and
returns tuples, strings, ints and stdlib types, never a `brig` type. A driver in
`presentation/drivers/` is the only caller that knows what this data means to the
domain's effects in `domain/effects.py`.
"""

import errno
import os
import resource
import signal
import time
from collections.abc import Mapping
from dataclasses import dataclass

_REAP_POLL_INTERVAL_S = 0.01
"""How often a deadline-bound wait re-checks `os.waitpid` -- short enough that a
deadline is honoured close to when it passes, long enough not to spin the CPU.
"""

_FD_SCAN_CAP = 4096
"""Upper bound on the bounded fd scan `_open_inheritable_fds` falls back to where
there is no `/proc/self/fd` to list (macOS). Capped well below `RLIMIT_NOFILE`'s soft
limit, which can run past a million on modern hosts: probing every number up to that
measures at ~18ms a spawn on this machine (one `os.get_inheritable` syscall each,
almost all of them past whatever is actually open), against ~1ms at this cap -- a
jail's command still has to run and exit after it, so paying double digits of
milliseconds just to find nothing is a bound this scan should not need to accept.
The gap this leaves: an inheritable fd open at a number past this cap survives into
the jail uncounted, on a platform with no cheaper way to enumerate what is actually
open -- unusual enough (four thousand fds open at once) that TASK-0001.05 does not
treat closing it as part of this hole.
"""


def _open_inheritable_fds() -> frozenset[int]:
    """Find every fd in this process that is both open and inheritable right now.

    Lists `/proc/self/fd` where it exists (Linux): the exact set, no scan needed.
    Falls back, elsewhere (macOS), to probing every fd number up to the process's
    soft `RLIMIT_NOFILE` or `_FD_SCAN_CAP`, whichever is lower -- there is no
    directory to list there. Either way, `os.get_inheritable` is asked of each
    candidate inside its own `try`: on the `/proc` path this also discards the
    directory fd `os.listdir` itself opened and closed before returning, which
    the listing can still name; on the scan path it is what tells an open fd from
    one no process ever opened.
    """
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


def _close_actions(inheritable_fds: tuple[int, ...]) -> list[tuple[int, int]]:
    """Build one `os.POSIX_SPAWN_CLOSE` file action per open, inheritable fd that
    `inheritable_fds` does not name.

    `os.posix_spawn`'s `file_actions` has no single "close everything except these"
    action, so this enumerates what is actually open and inheritable
    (`_open_inheritable_fds`) and states the close explicitly for each one outside
    the allow-list -- never for `inheritable_fds` itself, which grants the jailed
    process permission to keep a fd, not an instruction to force it open.
    """
    allowed = set(inheritable_fds)
    return [
        (os.POSIX_SPAWN_CLOSE, fd) for fd in sorted(_open_inheritable_fds()) if fd not in allowed
    ]


@dataclass(frozen=True)
class SpawnedProcess:
    """A process `spawn` started: its pid, the pgid of the group it leads, and whether
    its session was detached as well as its group.

    `spawn` always makes its child the leader of a new process group, by whichever of
    the two mechanisms its interpreter offers (see `spawn`), and both of them give that
    group the child's own pid -- so `pgid` here is always equal to `pid`, carried as its
    own field rather than folded away so a caller reads a process's identity as one
    value without recomputing the equality itself.

    `session_detached` is the half that is not always available: `True` when the child
    also leads a session of its own, with no controlling terminal, and `False` when only
    the process group could be made new. Teardown needs the group and nothing more
    (`signal_group`, `group_alive`), so it reads the same on either path; what differs
    is the TIOCSTI hole a shared controlling terminal leaves open, which a detached
    session closes and a new process group alone does not. Reported as plain data rather
    than left for a caller to infer from the platform, because a boundary that silently
    holds on one interpreter and not another is the one thing a library that grades
    boundaries must not have: a test that can only demonstrate the property where it
    exists reads this and reports itself not run elsewhere, instead of counting a
    denial that never happened as a pass.
    """

    pid: int
    pgid: int
    session_detached: bool


@dataclass(frozen=True)
class ProcessUnknown:
    """Sentinel `reap` and `reap_deadline` return in place of an exit code when `pid`
    is no longer this process's child to wait for at all (`ECHILD`): something else --
    another `reap`, `reap_nowait` or `reap_deadline` call that ran first, or an
    embedder that reaps its own children -- already collected it, and its exit code
    cannot be recovered now.

    Kept distinct from `reap_deadline`'s `None`, which means something else entirely:
    the clock reached `deadline` first with the process still running and left
    unreaped, so a later wait can still succeed. Collapsing the two into one value
    would make a deadline still worth retrying and a process that will never answer
    again look identical to every caller downstream (TASK-0001.06 review).
    """


class SpawnError(Exception):
    """Raised when `spawn` could not start `argv` as a new process.

    Args:
        argv: The command that could not be run.
        errno: The `OSError.errno` the OS reported for the failed spawn.
    """

    def __init__(self, argv: tuple[str, ...], *, errno: int) -> None:
        super().__init__(f"could not spawn {argv!r}: {os.strerror(errno)}")
        self.argv = argv
        self.errno = errno


def _spawn_leading_a_new_group(
    argv: tuple[str, ...],
    spawn_env: dict[str, str],
    file_actions: list[tuple[int, int]],
) -> tuple[int, bool]:
    """Start `argv` with `os.posix_spawnp` as the leader of a new process group, and
    report its pid together with whether its session was detached too.

    Asks for `setsid=True` first, which makes the child a session leader with no
    controlling terminal and puts it in a new process group of its own pid in the one
    step. Where the running interpreter was built without that flag it raises
    `NotImplementedError` -- during `posix_spawnp`'s own argument parsing, before any
    fork, so nothing has been started and a second call is safe -- and this retries with
    `setpgroup=0`, which POSIX always provides and which gives the child a new process
    group of its own pid but leaves it in the caller's session.

    Measured, rather than inferred from `sys.platform` (TASK-0001.12): the flag's
    availability is a property of the interpreter *build*, not of the OS. CPython's
    `posixmodule.c` tests `#ifdef POSIX_SPAWN_SETSID` at compile time; glibc declares
    that macro in `<spawn.h>` only from 2.26 onward, and uv's managed CPython (every
    version from 3.12 to 3.15, both arches, freethreaded included) is a
    python-build-standalone build compiled against a glibc 2.17 sysroot, so the flag is
    compiled out of it permanently however new the glibc it later runs against. Ubuntu's
    own packaged CPython, on that very same glibc 2.39, has it. So no platform check
    could answer this and only asking does; `NotImplementedError` is caught narrowly,
    around that one call, so no other source of it can quietly downgrade the guarantee.

    An `OSError` from either call propagates to `spawn`, which turns it into
    `SpawnError`.
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
) -> SpawnedProcess:
    """Start `argv` as a new process, the leader of a process group of its own, and of a
    session of its own where this interpreter can ask for one.

    Runs `argv` with `os.posix_spawnp`, which searches `PATH` for `argv[0]` as
    `execvp` does. The fork and the exec both happen inside the platform's C library,
    not in Python bytecode running after a fork -- unlike a plain `os.fork()` followed
    by `os.setsid()`, `os.chdir()` and `os.execvpe()` in the child, none of which is
    async-signal-safe: in a multi-threaded embedder, a forked child running that code
    can deadlock on a lock another thread held at the moment of the fork, and the
    parent is then left waiting on a child that can never answer. Both mechanisms
    `_spawn_leading_a_new_group` picks between keep that property -- each is a flag
    `posix_spawnp` acts on inside the C library, not code this process runs after a fork
    -- so the choice between them costs nothing in fork safety.

    What it does cost is stated in `SpawnedProcess.session_detached`, which says which
    of the two ran. Either way the new process leads a process group taking its own pid,
    which is what makes the walking skeleton's jail one thing teardown can signal as a
    whole (`signal_group`, `group_alive`). Only on the `setsid=True` path is its session
    detached from the controlling terminal as well; where the flag is compiled out, that
    hole is left for the jail type's own argv to close, which is why bwrap's
    `--new-session` is stated in `domain/jail_types/bwrap.py` as that jail type's own
    policy rather than left to this function's side effect.

    `inheritable_fds` is the jail type's own complete allow-list (`domain/plan.py`'s
    `Plan.inheritable_fds`, TASK-0001.05 AC#1), carried here as plain data -- this
    module imports nothing from `brig` (decision-0001 rule 1). Every fd this process
    currently has open and inheritable, standard streams included, that is not named
    in `inheritable_fds` is closed in the new process before `argv[0]` runs, through
    one `os.POSIX_SPAWN_CLOSE` file action per such fd (`_close_actions`): an
    inherited fd an embedder marked inheritable for its own purposes (IPC, say) would
    otherwise bypass every other boundary the jail states, since a fd reaches past a
    mount namespace or a filesystem policy entirely. `os.posix_spawn`'s file actions
    have no single "close everything except these" action, so this enumerates what is
    actually open rather than guessing a range to close.

    `env` replaces the child's environment when given, otherwise it inherits this
    process's. There is no `cwd` parameter: `posix_spawn` has no file action for that
    which this platform exposes (and no `Spawn` effect in `domain/effects.py` carries
    one), and changing it the one other way available -- `os.chdir` in this process,
    around the call, for the new process to inherit -- would mutate the embedder's own
    working directory while other threads may be reading it, exactly the kind of
    process-wide side effect a library that "knows nothing of the programs that embed
    it" (decision-0001) must not have. A jail type that needs one adds it later, behind
    whatever safe mechanism its platform actually offers.

    If a close action names a fd that another thread of a multi-threaded embedder
    closes first, in the window between this function's own scan and the moment the
    OS actually performs that action, the OS fails the *whole* spawn with `EBADF`,
    not just that one action -- the same way a bad `argv[0]` does (TASK-0001.09,
    measured on this host, racing CPython's own GIL handoff included -- see that
    task's implementation notes). This function answers that by retrying once: on
    `EBADF` only, it re-runs `_close_actions` -- a fresh scan -- and tries the spawn
    again with whatever that fresh scan finds. That fresh scan is not guaranteed
    correct, only much likelier to be: the fd the first attempt tripped over is
    settled closed by the time the retry scans (that EBADF is proof its own race
    already resolved), but nothing stops some other fd losing the same race against
    the retry's own, separate, equally narrow window -- which is exactly why a second
    `EBADF` is not retried again and surfaces as `SpawnError` instead of looping:
    a fd landing in that window twice in a row, on two different attempts, is a
    hazard belonging to whatever is closing fds that aggressively, not one this
    function can absorb without limit. Confirming each fd open immediately before
    the call was the other option this task's filing named; it was rejected because
    it only narrows the same window rather than closing it (the confirm and the OS's
    own close are still two separate steps, racing exactly as before, just over a
    shorter gap), while doubling the scan's cost on every spawn, racing or not.

    Raises:
        SpawnError: `argv[0]` could not be found on `PATH` or exec'd, or a close
            action's fd lost the race twice in a row (see above); its `errno` says
            which.
    """
    spawn_env = dict(env) if env is not None else dict(os.environ)
    try:
        pid, session_detached = _spawn_leading_a_new_group(
            argv, spawn_env, _close_actions(inheritable_fds)
        )
    except OSError as exc:
        if exc.errno != errno.EBADF:
            raise SpawnError(argv, errno=exc.errno if exc.errno is not None else 0) from exc
        try:
            pid, session_detached = _spawn_leading_a_new_group(
                argv, spawn_env, _close_actions(inheritable_fds)
            )
        except OSError as retry_exc:
            raise SpawnError(
                argv, errno=retry_exc.errno if retry_exc.errno is not None else 0
            ) from retry_exc
    return SpawnedProcess(pid=pid, pgid=pid, session_detached=session_detached)


def reap(pid: int) -> int | ProcessUnknown:
    """Wait for `pid` to exit, and return its exit code.

    A process that exited normally reports that exit code; one a signal killed
    reports the negative of the signal's number -- `os.waitstatus_to_exitcode`'s own
    convention, carried through unchanged.

    Returns:
        `ProcessUnknown` instead, without blocking, if `pid` is no longer this
        process's child to wait for at all (`ECHILD`). This can happen to a jail's
        leader whose group outlives it: an earlier, non-blocking `reap_nowait` call
        (teardown's `Verify` runs one ahead of every check) may already have
        collected it before this call runs (TASK-0001.06 review) -- a race to report,
        not a reason to let the raw `ChildProcessError` escape.
    """
    try:
        _, status = os.waitpid(pid, 0)
    except ChildProcessError:
        return ProcessUnknown()
    return os.waitstatus_to_exitcode(status)


def reap_deadline(pid: int, deadline: float) -> int | None | ProcessUnknown:
    """Wait for `pid` to exit, giving up once `time.monotonic()` passes `deadline`.

    `os.waitpid` has no timeout of its own, so this polls `os.waitpid(pid,
    os.WNOHANG)` on an interval short enough to honour `deadline` closely, instead of
    blocking on it the way `reap` does -- the fix for a jailed process that never
    exits hanging the embedder forever. `deadline` is a `time.monotonic()` timestamp,
    matching `domain/effects.py`'s `Reap.deadline`; this module does no I/O-free
    decision making of its own, so it is handed in rather than computed here.

    Returns:
        The exit code `os.waitstatus_to_exitcode` reports for `pid`, if it exits
        before `deadline`. `None` if the clock reaches `deadline` first, with `pid`
        left unreaped -- a later call (another `reap_deadline`, or a plain `reap`)
        still collects it. `ProcessUnknown` instead -- never `None` -- if `pid` is no
        longer this process's child to wait for at all (`ECHILD`: something else,
        such as an embedder that reaps its own children, already collected it): unlike
        a deadline that merely passed, no later call will ever collect an exit code
        for it either (TASK-0001.06 review).
    """
    while True:
        try:
            reaped_pid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return ProcessUnknown()
        if reaped_pid != 0:
            return os.waitstatus_to_exitcode(status)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(_REAP_POLL_INTERVAL_S, remaining))


def signal_group(pgid: int, sig: signal.Signals) -> None:
    """Send `sig` to every process in the group `pgid`.

    A no-op if the group is already gone by the time this runs: the teardown ladder
    that calls this verifies the group is alive immediately before each call, so that
    is a race to report, not the ordinary path, and there is nothing left to signal
    either way. `os.killpg` can answer that race with `ProcessLookupError` (ESRCH, the
    group fully gone) or, measured on this host (macOS, Darwin 27; TASK-0001.08), with
    `PermissionError` (EPERM): between a leader's exit and pid 1 reaping the group
    member it leaves behind, a signal to that zombie gets a permission answer instead
    of ESRCH, even though the group is -- for every purpose brig cares about -- just as
    gone. Caught broadly (`OSError`, not only the two measured errnos) rather than by
    name, because this function's job is to leave nothing of the attempt for the
    caller to see, not to enumerate every errno this platform's `killpg(2)` can raise
    for a group this process itself just spawned, and because this is infra: it hands
    back plain data only, never raises a `brig` type (decision-0001 rules 1 and 9), and
    a signal attempt against an already-gone group is not failure data worth reporting
    either -- the next `Verify` in the ladder is what the caller actually acts on.
    """
    try:
        os.killpg(pgid, sig)
    except OSError:
        pass


def reap_nowait(pid: int) -> int | None:
    """Collect `pid`'s exit status if it has already exited, without blocking.

    Teardown's verify calls this ahead of `group_alive` so an exited-but-unreaped
    process (a zombie, counted alive by any plain existence check) is collected and
    freed before that check runs, rather than answering "alive" forever. Returns the
    exit code `os.waitstatus_to_exitcode` reports for `pid` if it had already exited
    and this call is what collected it; `None` if it is still running, or if `pid` is
    no longer this process's child to wait for at all (`ECHILD`: something else --
    `reap` itself, on an earlier verify -- already collected it).
    """
    try:
        reaped_pid, status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return None
    if reaped_pid == 0:
        return None
    return os.waitstatus_to_exitcode(status)


def group_alive(pgid: int) -> bool:
    """Report whether any process in the group `pgid` is still alive.

    Signals the whole group with `0`, which sends nothing but still raises an
    exception once no member answers to it -- `killpg(2)`'s own way to probe a group
    without acting on it. Sound for any number of members, unlike probing one pid;
    still answers `True` for a pid whose sole process is a zombie, which is why
    `reap_nowait` runs first wherever this does.

    The OS answers that "nothing left to signal" case with `ProcessLookupError`
    (ESRCH) when the group has fully vanished, but, measured on this host (macOS,
    Darwin 27; TASK-0001.08), can instead answer `PermissionError` (EPERM): between a
    leader's exit and pid 1 reaping the group member it leaves behind, a probe of
    that zombie gets a permission answer rather than ESRCH, for a `pgid` this process
    spawned moments earlier and still owns -- not another process reusing the pgid.
    The group is, for every purpose this probe exists to answer, gone either way, so
    every `OSError` the probe can raise -- not only the two measured here -- answers
    `False`, the same plain-data shape `ProcessLookupError` already did: this is
    infra, which hands back plain data only and never raises (decision-0001 rules 1
    and 9), so nothing this probe can hit may escape as a raised exception instead of
    an answer.
    """
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    return True
