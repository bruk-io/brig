"""E2E gateway test for `brig.infra.processes` (TASK-0001.06 review, TASK-0001.08,
decision-0003/TASK-0013).

Decision-0001 rule 4 lets an e2e test import one `brig.infra` module directly, for
exactly this: a real `ECHILD` race against the real OS, with nothing faked and no
bwrap involved. This covers the review's reproduction directly -- a pid that is no
longer this process's child to wait for at all, because something else already
collected it -- which `reap` and `reap_deadline` must survive by returning
`ProcessUnknown` instead of leaking a raw `ChildProcessError`, and which
`reap_deadline` must tell apart from an ordinary deadline passing (`None`), since
only the second outcome leaves anything still worth waiting for. Pure POSIX process
primitives, so this runs for real on every host, including macOS.

decision-0003/TASK-0013's own audit of every call site into `reap`/`reap_deadline`
found none outside `teardown.py`'s own ladder that need the pid-reuse hazard closed
(cleanup-only callers that just want an exit code, never a check-then-act on the same
identity) -- so `reap`/`reap_deadline` keep today's always-release behaviour
unchanged, and this file's own existing assertions below are not contradicted by that
decision the way its own Consequences section first predicted. `peek`/`release`
(decision-0003's actual peek-before-release split) are new, standalone functions
instead, with their own coverage added below rather than folded into the unchanged
tests above them.

TASK-0001.08's own gateway test (below, AC#3) drives `destroy_jail` itself -- the
full public API, not just one infra function -- through the same rule-4 allowance:
it imports `brig`'s public API alongside `brig.infra.processes`, never
`brig.domain` or `brig.presentation`, so `Jail`'s `process` field (typed to
`brig.domain.effects.Process`, which this layer may not import) is filled with the
real `SpawnedProcess` this test's own `spawn` call returns, through `cast` rather
than a domain import -- every reader downstream of `Jail.process` (the driver, the
teardown ladder) only ever reads its `.pid`/`.pgid`, which `SpawnedProcess` already
carries, so nothing about the real teardown path changes; only the type checker
needs telling.

TASK-0001.21: `Jail.supervisors` lost its module-level default once every jail got
its own fresh `LiveSupervisors` instead of one shared singleton, so this test now
builds a real one of its own, `brig.infra.supervisor.link.LiveSupervisors` -- a
second `brig.infra` module, still within rule 4's allowance (the e2e layer bars
only `brig.domain`/`brig.presentation`, not a count of `brig.infra` modules).
`LiveSupervisors(())` is not a fake standing in for anything (rule 5 confines
doubles to `tests/integration/`): this test never calls `run_jail`, so `start`
(the only method that ever reads the empty `supervisor_argv`) is never called
either, and `destroy_jail`'s own `close(pid)` on a pid nothing started is a
documented real no-op (`LiveSupervisors.close`'s own docstring) -- the genuine
production path for a jail destroyed before anything was ever started through it,
not a simulation of one. `cast`, the same way `Jail.process` already needed one:
`LiveSupervisors.await_done` returns this module's own `SupervisorDoneUnknown`,
not `presentation.ports`'s mirror of it (`ports.py`'s own docstring explains why
the two are deliberately not the same type), so `SupervisorPort`'s structural
shape is satisfied in substance, by the real production class itself, but not
in a way mypy can see without crossing into `presentation` -- exactly what this
layer may not import -- to fetch the one adapter (`presentation/api.py`'s
`_real_supervisor_port`) that translates between them.
"""

import os
import signal
import time
from typing import Any, cast

from brig import Jail, JailTeardownFailed, destroy_jail
from brig.infra.processes import ProcessUnknown, peek, reap, reap_deadline, release, spawn
from brig.infra.supervisor.link import LiveSupervisors

_STDIO_FDS = (0, 1, 2)
"""The allow-list these reap/reap_deadline tests pass `spawn`: standard streams only,
since what they exercise is the ECHILD race, not TASK-0001.05's fd-closing policy.
"""

_LEADER_EXITS_BEFORE_GROUP_ARGV = ("/bin/sh", "-c", "trap '' TERM; sleep 30 & exit 0")
"""A leader that ignores TERM, forks a child that outlives it, and exits right away --
the exact shape TASK-0001.08 measured raising `PermissionError` (EPERM) out of
`group_alive` roughly 2 times in 25 on this host (macOS, Darwin 27), through the race
between the leader's exit and its reaping.
"""

_LEADER_EXITS_BEFORE_GROUP_ITERATIONS = 150
"""High enough that the pre-fix race (measured at ~2/25, and again at ~2/60) would be
all but certain to show at least one `PermissionError` if it still could; the fix
removes the race entirely rather than narrowing its window, so the count this test
asks for is about confidence in a real run, not about tuning odds.
"""


def _spawn_and_reap_directly(argv: tuple[str, ...]) -> int:
    """Spawn `argv` and collect it with a raw `os.waitpid`, standing in for something
    other than `brig.infra.processes` reaping it first.
    """
    process = spawn(argv, _STDIO_FDS)
    os.waitpid(process.pid, 0)
    return process.pid


def test_reap_returns_process_unknown_once_something_else_already_collected_it() -> None:
    """`reap` tolerates `ECHILD` instead of leaking it (review finding 1 and 2)."""
    pid = _spawn_and_reap_directly(("true",))

    assert reap(pid) == ProcessUnknown()


def test_reap_deadline_returns_process_unknown_once_something_else_already_collected_it() -> None:
    """`reap_deadline` also tolerates `ECHILD`, and distinguishes it from a timeout
    (review finding 3).
    """
    pid = _spawn_and_reap_directly(("true",))

    assert reap_deadline(pid, time.monotonic() + 5.0) == ProcessUnknown()


def test_reap_deadline_returns_none_on_a_genuine_timeout_not_process_unknown() -> None:
    """A deadline that merely passed, with the process still running, is `None` --
    never `ProcessUnknown` -- so a later wait still gets a chance to collect it.
    """
    process = spawn(("sleep", "9999"), _STDIO_FDS)
    try:
        result = reap_deadline(process.pid, time.monotonic() + 0.05)
        assert result is None
    finally:
        os.kill(process.pid, signal.SIGKILL)
        reap(process.pid)


def _peek_until_exited(pid: int, deadline: float) -> int | None | ProcessUnknown:
    """Poll `peek` until it reports something other than "still running", or
    `deadline` passes -- `peek` itself never blocks, so a caller that wants to
    observe a fast-exiting process's own exit (`true`, here) without a blocking
    `reap` (which would also release it) polls instead.
    """
    while True:
        outcome = peek(pid)
        if outcome is not None or time.monotonic() >= deadline:
            return outcome
        time.sleep(0.001)


def test_peek_observes_an_exited_process_without_releasing_its_pid() -> None:
    """`peek` reports the same exit status twice in a row (decision-0003): unlike
    `reap`, it never consumes the zombie it observes, so a second `peek` call sees
    exactly what the first one did, not `ProcessUnknown`.
    """
    process = spawn(("true",), _STDIO_FDS)
    try:
        first = _peek_until_exited(process.pid, time.monotonic() + 5.0)
        second = peek(process.pid)
        assert first == 0
        assert second == first
    finally:
        release(process.pid)


def test_peek_on_a_still_running_process_returns_none_without_blocking() -> None:
    """`peek` on a process that has not exited yet returns `None` immediately,
    never blocking the way a plain `reap` would.
    """
    process = spawn(("sleep", "9999"), _STDIO_FDS)
    try:
        assert peek(process.pid) is None
    finally:
        os.kill(process.pid, signal.SIGKILL)
        reap(process.pid)


def test_release_frees_the_pid_and_a_later_peek_reports_process_unknown() -> None:
    """`release`, called after `peek` has already observed a process exited,
    performs the real reap: a `peek` afterward reports `ProcessUnknown`, the same
    answer it would give for a pid something else entirely had already collected.
    """
    process = spawn(("true",), _STDIO_FDS)
    assert _peek_until_exited(process.pid, time.monotonic() + 5.0) == 0

    release(process.pid)

    assert peek(process.pid) == ProcessUnknown()


def test_release_on_a_still_running_process_is_a_no_op() -> None:
    """`release` called before a process has exited does not block, and releases
    nothing: a later `peek` still correctly observes it, running or already
    exited by then, but never `ProcessUnknown` -- release had nothing to collect.
    """
    process = spawn(("sleep", "0.2"), _STDIO_FDS)
    try:
        release(process.pid)  # nothing to release yet -- must not block
        assert peek(process.pid) != ProcessUnknown()
    finally:
        reap(process.pid)


def test_destroy_jail_survives_the_leader_exiting_before_its_group() -> None:
    """TASK-0001.08 AC#3: no stdlib exception reaches an embedder from `destroy_jail`.

    Drives the leader-exits-before-its-group shape
    (`_LEADER_EXITS_BEFORE_GROUP_ARGV`) through `destroy_jail` itself, in a loop
    (`_LEADER_EXITS_BEFORE_GROUP_ITERATIONS` times), and records the type of
    anything `destroy_jail` raises. What this asserts against: a raw
    `PermissionError`, `ProcessLookupError` or other `OSError` escaping
    `group_alive` or `signal_group` inside the ladder, which is exactly what
    TASK-0001.06/.08 fixed in `infra/processes.py`.

    decision-0003/TASK-0013: `JailTeardownFailed` was allowed and expected here on
    some iterations, as the correctly-typed outcome of the TASK-0001.07 timing race
    (the kill ladder's post-KILL verify could still see a group mid-death). That
    race is now closed by the post-KILL rung's own bounded grace-window poll
    (`destroy_jail`'s default `kill_grace_s`), measured directly against this exact
    reproduction in `brig-probe-amd64:latest` (200/200 clean with the default grace
    window; 100/200 `JailTeardownFailed` with it set to `0.0`, confirming the window
    is what closes it, not that the race stopped existing) -- so this loop no longer
    tolerates `JailTeardownFailed` either.
    """
    escaped: list[BaseException] = []
    teardown_failed = 0

    for _ in range(_LEADER_EXITS_BEFORE_GROUP_ITERATIONS):
        spawned = spawn(_LEADER_EXITS_BEFORE_GROUP_ARGV, _STDIO_FDS)
        time.sleep(0.05)
        jail = Jail(process=cast(Any, spawned), supervisors=cast(Any, LiveSupervisors(())))
        try:
            destroy_jail(jail)
        except JailTeardownFailed:
            teardown_failed += 1
        except Exception as exc:
            escaped.append(exc)
        finally:
            try:
                os.killpg(spawned.pgid, signal.SIGKILL)
            except OSError:
                pass

    assert escaped == [], (
        f"non-brig exception(s) escaped destroy_jail: {[type(exc).__name__ for exc in escaped]}"
    )
    assert teardown_failed == 0, (
        f"{teardown_failed} iteration(s) raised JailTeardownFailed -- the post-KILL "
        "grace window should have closed this race"
    )


def test_destroy_jail_does_not_misread_a_long_held_zombie_as_alive() -> None:
    """The exact scenario decision-0003 measured as broken: a single-process
    jail's own leader, already exited and sitting as an un-released zombie,
    answers `group_alive` `True` on Linux through a plain `killpg(pgid, 0)` --
    indistinguishable there from a genuinely alive group -- unless the pid known
    to be deliberately held is excluded (`group_alive`'s own `held` parameter).

    Widens the peek-before-release window far past anything a real teardown ever
    takes, by sleeping a full second between the leader exiting and `destroy_jail`
    ever looking at it, before driving `destroy_jail` itself -- the real
    production path, not a raw `group_alive` call -- against it. A misread here
    would send TERM and KILL for a group with nothing left to signal, then burn
    the whole `kill_grace_s` grace window before finally giving up with
    `JailTeardownFailed`; this proves instead that the very first `Verify` reads
    the already-exited, still-held leader as gone, correctly, on whichever
    platform this runs.
    """
    spawned = spawn(("true",), _STDIO_FDS)
    time.sleep(1.0)  # deliberately widen the peek-before-release window
    jail = Jail(process=cast(Any, spawned), supervisors=cast(Any, LiveSupervisors(())))

    started = time.monotonic()
    destroy_jail(jail, kill_grace_s=5.0)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, (
        f"destroy_jail took {elapsed:.2f}s -- a misread zombie-as-alive would "
        "escalate signals for nothing and burn the whole 5s grace window"
    )
