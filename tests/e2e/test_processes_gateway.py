"""E2E gateway test for `brig.infra.processes` (TASK-0001.06 review, TASK-0001.08).

Decision-0001 rule 4 lets an e2e test import one `brig.infra` module directly, for
exactly this: a real `ECHILD` race against the real OS, with nothing faked and no
bwrap involved. This covers the review's reproduction directly -- a pid that is no
longer this process's child to wait for at all, because something else already
collected it -- which `reap` and `reap_deadline` must survive by returning
`ProcessUnknown` instead of leaking a raw `ChildProcessError`, and which
`reap_deadline` must tell apart from an ordinary deadline passing (`None`), since
only the second outcome leaves anything still worth waiting for. Pure POSIX process
primitives, so this runs for real on every host, including macOS.

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
"""

import os
import signal
import time
from typing import Any, cast

from brig import Jail, JailTeardownFailed, destroy_jail
from brig.infra.processes import ProcessUnknown, reap, reap_deadline, spawn

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


def test_destroy_jail_survives_the_leader_exiting_before_its_group() -> None:
    """TASK-0001.08 AC#3: no stdlib exception reaches an embedder from `destroy_jail`.

    Drives the leader-exits-before-its-group shape
    (`_LEADER_EXITS_BEFORE_GROUP_ARGV`) through `destroy_jail` itself, in a loop
    (`_LEADER_EXITS_BEFORE_GROUP_ITERATIONS` times), and records the type of
    anything `destroy_jail` raises. `JailTeardownFailed` is allowed and expected on
    some iterations -- the correctly-typed outcome of the separate, already-tracked
    TASK-0001.07 timing race (the kill ladder's post-KILL verify can still see a
    group that is in the middle of dying) -- as is no exception at all, when the
    ladder's own TERM/KILL escalation finishes the group off before its last
    `Verify`. What this asserts against is anything else: a raw `PermissionError`,
    `ProcessLookupError` or other `OSError` escaping `group_alive` or `signal_group`
    inside the ladder, which is exactly what this task fixed in
    `infra/processes.py`.
    """
    escaped: list[BaseException] = []

    for _ in range(_LEADER_EXITS_BEFORE_GROUP_ITERATIONS):
        spawned = spawn(_LEADER_EXITS_BEFORE_GROUP_ARGV, _STDIO_FDS)
        time.sleep(0.05)
        jail = Jail(process=cast(Any, spawned))
        try:
            destroy_jail(jail)
        except JailTeardownFailed:
            pass
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
