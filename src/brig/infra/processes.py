"""Processes: spawn one, signal its group, reap it, read whether a pid is alive.

Plain data in, plain data out (decision-0001 rule 1): every function here takes and
returns tuples, strings, ints and stdlib types, never a `brig` type. A driver in
`presentation/drivers/` is the only caller that knows what this data means to the
domain's effects in `domain/effects.py`.

decision-0003's peek-before-release split: `peek` observes a pid's exit status
without releasing it for reuse (`os.waitid`'s own `WNOWAIT`), and `release` performs
the real release later, once nothing will ever peek or wait on that pid again --
closing the raw pid-reuse hazard a plain, unconditional reap left open for a pid
teardown's own ladder still needs to check again after observing it exited.
`group_alive`'s own `held` parameter and `group_alive_deadline` are the group-level
counterpart: a deliberately held, peeked-not-released zombie must not itself read as
"this group is still alive."
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
"""How often a deadline-bound wait re-checks its condition -- short enough that a
deadline is honoured close to when it passes, long enough not to spin the CPU. Shared
by `reap_deadline` (polls `os.waitpid`) and `group_alive_deadline` (polls `peek` and
`group_alive`): the same tradeoff, not two independently tuned numbers.
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


def _close_actions(
    inheritable_fds: tuple[int, ...], *, protect: frozenset[int] = frozenset()
) -> list[tuple[int, int]]:
    """Build one `os.POSIX_SPAWN_CLOSE` file action per open, inheritable fd that
    `inheritable_fds` does not name.

    `os.posix_spawn`'s `file_actions` has no single "close everything except these"
    action, so this enumerates what is actually open and inheritable
    (`_open_inheritable_fds`) and states the close explicitly for each one outside
    the allow-list -- never for `inheritable_fds` itself, which grants the jailed
    process permission to keep a fd, not an instruction to force it open.

    `protect` is `_fd_actions`'s own resolved source fd numbers (`spawn`'s `fds`,
    after `_resolve_fd_sources`), kept out of this enumeration on top of
    `inheritable_fds` for the same reason: a `dup2` file action later in the same
    list needs its source fd to still be open when it runs. In practice `os.pipe`'s
    and `os.dup`'s own fds are never inheritable (PEP 446's default), so
    `_open_inheritable_fds` would not find them regardless -- `protect` states that
    explicitly rather than leaning on an unstated default surviving unnoticed.
    """
    allowed = set(inheritable_fds) | protect
    return [
        (os.POSIX_SPAWN_CLOSE, fd) for fd in sorted(_open_inheritable_fds()) if fd not in allowed
    ]


def _resolve_fd_sources(fds: Mapping[int, int]) -> tuple[dict[int, int], tuple[int, ...]]:
    """Rewrite `fds` (new process's fd -> this process's own fd) so that no source
    value collides with any target value, and report which extra fds of this
    process's own the rewrite opened to do it.

    `os.posix_spawn`'s `DUP2` file action is specified to do *nothing at all* --
    not even clear the close-on-exec flag a freshly-opened pipe fd carries by
    default (PEP 446) -- when its source and target are the same number
    (`dup2(fd, fd)`). A source that already sits at its own target by sheer
    allocation order is the common case here, not a rare one: an otherwise
    unencumbered process's very first `os.pipe()` call returns the next fd past
    whatever is already open, which is exactly `3` the moment this process has
    nothing else open past its own standard streams -- the same number
    `infra/supervisor/wire.py`'s own `REQUEST_FD` names. Processing several pairs
    in a fixed order has the same hazard one level up: a source that happens to
    sit at some *other* pair's target would be silently overwritten before its
    own `DUP2` ever reads it.

    Every source fd `fds` names that collides with any target fd `fds` names --
    its own included -- is relocated onto a number past every target, and the
    original is left exactly as it was: closing it here, before the spawn that
    still needs the duplicate even runs, would be premature. The caller closes
    every fd this function reports in its own second return value, once that
    spawn attempt (every retry included) is done with it.

    A bare `os.dup` cannot do this relocating: it always returns this process's
    *lowest* free fd, and a target number is free -- hence a candidate --
    whenever this process happens to have a hole there, which is the common
    case, not a rare one (an unencumbered process's first `os.pipe()` lands at
    `3`, a number `fds` itself may name as a target). `fcntl.F_DUPFD` instead
    takes a floor: the lowest free fd *at or above* a number this function
    chooses, so asking for one past `max(targets)` guarantees the result falls
    outside the full target set regardless of which numbers below that floor
    happen to be free.
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
    """Build the file actions that give the new process the fds `resolved_fds`
    names (new process's fd -> this process's own fd, already resolved so no
    source collides with any target -- `_resolve_fd_sources`), in place of
    whichever of those numbers it would otherwise have inherited unchanged.

    One `os.POSIX_SPAWN_DUP2` per pair, then one `os.POSIX_SPAWN_CLOSE` per
    source fd's own number in the new process -- every `DUP2` runs before any
    `CLOSE`, so a source fd that also names some other pair's own target is
    still open and unchanged when its own `DUP2` reads it. Like every other file
    action `spawn` builds, each runs inside `posix_spawnp`'s own C-library step,
    before `argv[0]` execs: never Python bytecode running after a fork, so this
    costs nothing of the fork-safety `spawn`'s own docstring already explains.
    An empty `resolved_fds` builds no action at all, and every stream is
    inherited from this process exactly as it always was.

    No `CLOSE` ever names a number some `DUP2` just wrote a target onto: a
    source equal to one of `resolved_fds`'s own target numbers is excluded from
    the `CLOSE` list rather than closed, since that number's `DUP2` result --
    not the old source fd it displaced -- is the one this new process keeps.
    `_resolve_fd_sources` is the only caller and never hands this a source equal
    to a target, but that invariant is enforced once, here, rather than relied
    on silently at every call site.
    """
    actions: list[tuple[int, ...]] = [
        (os.POSIX_SPAWN_DUP2, source, target) for target, source in resolved_fds.items()
    ]
    close_fds = set(resolved_fds.values()) - set(resolved_fds)
    actions += [(os.POSIX_SPAWN_CLOSE, fd) for fd in sorted(close_fds)]
    return actions


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
    """Sentinel `reap`, `reap_deadline` and `peek` return in place of an exit code
    when `pid` is no longer this process's child to wait for at all (`ECHILD`):
    something else -- another `reap`/`reap_deadline`/`peek` call, a `release`, or an
    embedder that reaps its own children -- already released it, and its exit code
    cannot be recovered now.

    Kept distinct from `reap_deadline`'s `None`, which means something else entirely:
    the clock reached `deadline` first with the process still running and left
    unreaped, so a later wait can still succeed. Collapsing the two into one value
    would make a deadline still worth retrying and a process that will never answer
    again look identical to every caller downstream (TASK-0001.06 review).
    """


class SpawnError(Exception):
    """Raised when `spawn` could not start `argv` as a new process.

    Fires whenever `spawn`'s own pre-check cannot resolve `argv[0]` against
    `PATH` (`errno.ENOENT`), on every platform -- and, where the OS itself still
    raises for a failed exec after that (measured true on macOS), whenever that
    happens too. It does NOT fire, and cannot structurally be made to fire, for an
    `argv[0]` that resolves at pre-check time but whose exec fails later for some
    reason the OS reports as a plain exit code instead of a spawn failure: on
    Linux, glibc's own `posix_spawnp` takes that shape for an argv[0] that stops
    resolving between the pre-check and the real spawn (TASK-0014's own TOCTOU
    residual) -- it does not raise at all, and the child it starts anyway just
    exits 127, indistinguishable by exit code alone from a command that chose to
    exit 127 on its own.

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
    fds: Mapping[int, int] | None = None,
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

    `fds`, left `None` by default, redirects any of the new process's own fd numbers
    to a fd of this process's own instead of its ordinary inherited stream
    (`_resolve_fd_sources`/`_fd_actions`): one `os.POSIX_SPAWN_DUP2` apiece, performed
    inside `posix_spawnp`'s own C-library step like every other file action here,
    never by touching this process's own fds around the call -- the same "no
    process-wide side effect" reasoning this docstring's `cwd` paragraph already
    gives applies exactly as much to the embedder's own stdio. Keyed by the new
    process's own fd number rather than fixed to `0`/`1`: `infra/supervisor/link.py`
    uses this to connect the supervisor's own wire protocol to fds `3`/`4`
    (`infra/supervisor/wire.py`'s `REQUEST_FD`/`EVENTS_FD`), deliberately *not* `0`/
    `1` any more (DRAFT-0010) -- which leaves the new process's own `0`/`1`/`2` free
    to inherit from this process exactly as `argv` would without `fds` at all, so a
    supervised command started past it inherits them in turn, unchanged, the same
    way it would have with no supervisor in between.

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

    Before ever calling `os.posix_spawnp`, resolves `argv[0]` itself with
    `shutil.which`, against this process's own `os.environ.get("PATH",
    os.defpath)` -- deliberately *not* `env`'s own `PATH`, even where `env`
    overrides it -- and raises `SpawnError` proactively when it cannot resolve
    (TASK-0014). `env` only becomes the new process's own environment once exec
    succeeds; `posix_spawnp`'s own PATH search, measured directly against both
    Apple's libc and glibc, consults this calling process's own environment for
    that search regardless of what `env` says -- a POSIX wrinkle visible only by
    testing it (a bare `argv[0]` that resolves solely through a `PATH` given in
    `env` still spawns a child that exits 127 unexplained, the exact shape this
    task exists to catch, because the real search never looked there). This
    pre-check mirrors that, on purpose, so it predicts the real spawn below
    rather than some other, plausible-sounding, unmeasured mechanism.
    `shutil.which` already matches `execvp`'s own semantics for a name containing `/`:
    checked literally against that exact path, never PATH-searched -- but still
    checked for existence and executability, the same as a PATH-searched name. A
    missing direct path is therefore also caught here now, narrowing the Linux
    gap for that shape too (measured: `os.posix_spawnp` with a nonexistent
    direct path does not raise there either, the identical unexplained-exit-127
    shape a missing bare name has). Only the search step (PATH walk vs. literal
    check) differs from the bare-name case, not whether the pre-check applies.

    This narrows, but cannot close, the gap this function was filed against:
    glibc's own `posix_spawnp`, measured on Linux, does not raise at all for an
    `argv[0]` that cannot be resolved -- it returns a pid for a child that starts
    and immediately exits 127, indistinguishable from a command that chose that
    exit code itself. The common case (`argv[0]` never resolves at all) is
    caught here, before any spawn is attempted, on every platform. What is not
    caught is the TOCTOU race: `argv[0]` resolving at pre-check time but the
    binary vanishing before the real spawn runs a moment later. On macOS the OS's
    own `posix_spawnp` still raises `FileNotFoundError` for that, so `SpawnError`
    still fires; on Linux nothing does, and that race falls through to the same
    unexplained exit-127 shape as before this pre-check existed.

    Raises:
        SpawnError: `argv[0]` could not be resolved against `PATH` by this
            function's own pre-check, or a close action's fd lost the race
            twice in a row (see above); its `errno` says which.
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
        # `_resolve_fd_sources`'s own extra fds, opened only to dodge a collision
        # between some source and some target -- this process's one copy of each,
        # closed only now that every spawn attempt above (the retry included) is
        # done reading from it, success or failure either way.
        for fd in relocated:
            os.close(fd)
    return SpawnedProcess(pid=pid, pgid=pid, session_detached=session_detached)


def reap(pid: int) -> int | ProcessUnknown:
    """Wait for `pid` to exit, and return its exit code.

    A process that exited normally reports that exit code; one a signal killed
    reports the negative of the signal's number -- `os.waitstatus_to_exitcode`'s own
    convention, carried through unchanged.

    Returns:
        `ProcessUnknown` instead, without blocking, if `pid` is no longer this
        process's child to wait for at all (`ECHILD`). This can happen when an
        earlier `release` call (teardown's own terminal step, decision-0003) or an
        embedder's own reap already collected it before this call runs
        (TASK-0001.06 review) -- a race to report, not a reason to let the raw
        `ChildProcessError` escape.
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
        time.sleep(min(_POLL_INTERVAL_S, remaining))


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


def _exitcode_from_siginfo(info: os.waitid_result) -> int:
    """Convert a `os.waitid` siginfo result to `os.waitstatus_to_exitcode`'s own
    convention: the exit code for a process that exited normally, the negative of
    the signal number for one a signal killed.

    `waitid`'s own `si_status`/`si_code` is a different shape from `waitpid`'s raw
    status word, so `os.waitstatus_to_exitcode` -- built for the latter -- cannot be
    handed the former directly; this is the one place that does the translation by
    hand, for every caller below that uses `WEXITED` through `waitid` instead of a
    plain `waitpid`.
    """
    if info.si_code == os.CLD_EXITED:
        return info.si_status
    return -info.si_status


def peek(pid: int) -> int | None | ProcessUnknown:
    """Observe whether `pid` has exited, without releasing its pid for reuse.

    `os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)` (decision-0003):
    `WNOWAIT` reports a zombie's exit status without consuming it -- a later `peek`,
    or the real release (`release`, below), can still observe or collect it -- and
    `WNOHANG` keeps this non-blocking, since the caller (teardown's `Verify`) must
    not block on a jailed process that may never exit on its own.

    Returns:
        The exit code `_exitcode_from_siginfo` reports for `pid`, if it has already
        exited. `None` if it is still running. `ProcessUnknown` instead -- never
        `None` -- if `pid` is no longer this process's child to wait for at all
        (`ECHILD`): something else already released it, so no later peek or release
        will ever observe it either.
    """
    try:
        info = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
    except ChildProcessError:
        return ProcessUnknown()
    if info is None:
        return None
    return _exitcode_from_siginfo(info)


def release(pid: int) -> None:
    """Release `pid`'s exit status for real, so the OS is free to reuse its pid.

    The second half of decision-0003's peek-before-release split: a caller that has
    already observed `pid` exited through `peek` (or otherwise knows nothing will
    ever need to peek it again) calls this once teardown's own ladder is done with
    it, so a pid is never left a zombie forever but also never released -- and so
    reusable -- before every check that needed its identity stable has finished.

    `os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG)`: no `WNOWAIT`, so a pending
    zombie is actually collected, not merely observed; `WNOHANG` keeps this safe to
    call even where `pid` has not actually exited yet (nothing to release yet, so
    this is a no-op rather than a block) -- a caller that releases unconditionally
    once its own ladder ends, win or lose, must never hang on a process that is
    still genuinely running.

    A no-op, silently, if `pid` is no longer this process's child to wait for at all
    (`ECHILD`: something else already released it) -- release is idempotent, since
    nothing further needs this call to report anything once nothing is left to
    release (decision-0001 rules 1 and 9: infra hands back plain data only, never
    raises).
    """
    try:
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG)
    except ChildProcessError:
        pass


def _group_alive_proc_scan(pgid: int, held: frozenset[int]) -> bool:
    """Linux's own per-member answer to `group_alive`, for when `held` is non-empty:
    report whether anything in the group `pgid` *other than* a pid in `held` is
    still alive.

    `killpg(pgid, 0)` cannot make this distinction on Linux (decision-0003's own
    measurement: it answers "exists" identically for a group that is nothing but
    zombies and one with a genuinely alive member) -- enumerating `/proc` by hand is
    the one portable way to ask "which pids report this pgid, and which of those are
    not zombies," excluding the pid(s) a caller already knows are deliberately held.

    Reads `/proc/<pid>/stat` for every numeric entry of `/proc`, splitting each line
    on its *last* `)` -- `comm`, the field just before it, can itself contain parens,
    so only the last one is guaranteed to be the real field separator -- and reads
    state, ppid, pgrp as the first three whitespace-separated fields after that.
    Swallows `FileNotFoundError`/`ProcessLookupError`/`PermissionError` for any one
    entry: a process can exit mid-scan, or belong to another user whose `/proc`
    entry this one cannot read fully, and neither should fail the whole scan.
    """
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        candidate = int(name)
        if candidate in held:
            continue
        try:
            with open(f"/proc/{name}/stat") as handle:
                stat_line = handle.read()
        except FileNotFoundError, ProcessLookupError, PermissionError:
            continue
        _, _, rest = stat_line.rpartition(")")
        fields = rest.split()
        state, candidate_pgid = fields[0], fields[2]
        if int(candidate_pgid) == pgid and state != "Z":
            return True
    return False


def group_alive(pgid: int, held: frozenset[int] = frozenset()) -> bool:
    """Report whether anything in the group `pgid`, other than a pid named in
    `held`, is still alive.

    Signals the whole group with `0` by default (`killpg(pgid, 0)`, which sends
    nothing but still raises an exception once no member answers to it -- `killpg`'s
    own way to probe a group without acting on it). Sound for any number of
    members, unlike probing one pid; still answers `True` for a pid whose sole
    process is a zombie, which is why `peek` runs first wherever this does, and
    `held` names whichever pid that peek found already exited -- a deliberately
    held zombie must not itself read as "alive" (decision-0003).

    The OS answers `killpg`'s "nothing left to signal" case with `ProcessLookupError`
    (ESRCH) when the group has fully vanished, but, measured on this host (macOS,
    Darwin 27; TASK-0001.08), can instead answer `PermissionError` (EPERM): between a
    leader's exit and pid 1 reaping the group member it leaves behind, a probe of
    that zombie gets a permission answer rather than ESRCH. **Both still mean "gone"
    on macOS, including once a member is held** -- decision-0003's own mixed-case
    measurement (a held zombie leader alongside a genuinely-alive backgrounded
    sibling) found `killpg`'s EPERM narrower than first assumed: it appears only
    once the *entire* group has nothing left but zombies, not whenever any one
    member happens to be held. **Linux's `killpg` makes no such distinction at
    all** -- it answers "exists" the same way for an all-zombie group and a
    genuinely alive one, with nothing here to tell them apart -- so once `held` is
    non-empty this function instead asks `_group_alive_proc_scan` there, falling
    back to the `killpg` probe wherever `/proc` itself does not exist (any other
    platform, including macOS, where `held` is accordingly never consulted; TASK-
    0001.12's own lesson: ask by trying, never branch on `sys.platform`). Every
    `OSError` the `killpg` probe can raise -- not only the two measured here --
    answers `False`: this is infra, which hands back plain data only and never
    raises (decision-0001 rules 1 and 9).
    """
    if held:
        try:
            return _group_alive_proc_scan(pgid, held)
        except FileNotFoundError:
            pass
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    return True


def group_alive_deadline(pid: int, pgid: int, deadline: float) -> bool:
    """Poll `group_alive` until it reports gone, or `time.monotonic()` passes
    `deadline`.

    The kill ladder's post-KILL rung needs this, not a single immediate
    `group_alive` call (TASK-0001.07): `SignalKind.KILL` cannot be caught or
    ignored, but the kernel finishing what it started is not instantaneous, and a
    `Verify` run the instant after can still -- correctly, not as a bug -- see the
    group alive for a few more moments. Bounded, not open-ended, the same way
    `reap_deadline` bounds a wait that would otherwise block forever.

    Peeks `pid` (the group's leader) ahead of every `group_alive` call, exactly as
    `Verify`'s own immediate check does, so a leader that exits partway through this
    poll is excluded from the very next iteration's answer rather than counted alive
    forever as an unreaped zombie.

    Returns:
        `False` as soon as `group_alive` reports the group gone. `True` once
        `deadline` passes with `group_alive` still reporting something alive.
    """
    while True:
        outcome = peek(pid)
        held = frozenset({pid}) if isinstance(outcome, int) else frozenset()
        if not group_alive(pgid, held):
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(_POLL_INTERVAL_S, remaining))
