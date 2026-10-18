"""E2E battery for the spawn close-action race (TASK-0001.09 AC#2).

`infra/processes.py`'s `spawn` scans this process's open, inheritable fds and builds
one `os.POSIX_SPAWN_CLOSE` file action per fd outside the caller's allow-list, then
hands that list to `os.posix_spawnp`. If another thread of a multi-threaded embedder
closes one of those fds in the window between the scan and the moment the OS performs
the action, the OS fails the *whole* spawn with `EBADF`, not just that one action.
TASK-0001.09's chosen fix (see its own implementation notes, and `spawn`'s docstring)
retries once on `EBADF`, rebuilding the close actions from a fresh scan.

Decision-0001 rule 4 lets an e2e test import one `brig.infra` module directly, for
exactly this: a real race against the real OS, with nothing faked and no bwrap
needed. Rule 5 forbids `unittest.mock`/`monkeypatch` anywhere in this suite; the
race below plants itself with a genuine second thread racing `spawn`'s own internal
scan and syscall, nothing patched or substituted.

Plantability is platform-dependent, measured rather than assumed (TASK-0001.09
notes carry the full counts):

- Where `_open_inheritable_fds` has no `/proc/self/fd` to list and falls back to
  probing every candidate fd one `os.get_inheritable` syscall at a time (macOS),
  that loop's many brief GIL-releasing syscalls give a second Python thread, with
  `sys.setswitchinterval` lowered, many chances to run its own `os.close` inside the
  scan-to-syscall window. Measured on this host: with the production fix reverted,
  a calibrated race there fails every spawn with `EBADF` (30/30, then 50/50 on a
  second run); restored, the same race never fails a spawn (50/50, then 20/20).
  That differential is the proof this task's AC#2 asks for; it is not repeated as a
  live revert-and-restore inside this suite (rule 5's doubles live only in
  `tests/integration/`, and reverting production code at test time is not that
  either, so it is recorded once, in the task's own implementation notes, the way
  TASK-0001.08's was) -- what runs here is the race itself, on the still-fixed code,
  asserting it no longer loses.
- Where `/proc/self/fd` exists and is listed directly (Linux), the scan is one fast
  listing plus a handful of per-fd syscalls for whatever is actually open, which
  empirically gives a racing Python thread far fewer chances to land inside the
  window: even with thousands of decoy fds open (to lengthen the scan to the same
  few milliseconds as the macOS path) and the same lowered switch interval, the
  racing thread's close consistently lands too late to matter -- the scan still
    reports the target fd open and the close call itself still reports success, but
    the spawn succeeds anyway in 60/60 trials, meaning the close reaches the parent's
    fd table only after the child has already forked its own copy and closed its own
    inherited fd before exec. That is a mechanistic negative (the parent-side close
    cannot reach an already-forked child within Python's own GIL-handoff
    granularity on this scan path), not evidence the hazard is absent on Linux --
    the OS-level mechanism (confirmed directly, no threading needed: closing a fd
    before naming it in a close action fails `os.posix_spawnp` with `EBADF` on both
    platforms) is identical either way.

So this battery runs only on the fallback-scan path (decision-0001's e2e rule: run
where the real thing exists, report "not run" elsewhere rather than pass vacuously).
"""

import os
import sys
import threading
import time

import pytest

from brig.infra.processes import ProcessUnknown, SpawnError, reap, spawn

_STDIO_FDS = (0, 1, 2)
"""The allow-list every spawn below grants beyond the one fd under test: standard
streams only, so the probe process can be started and reaped normally.
"""

_RACE_SWITCH_INTERVAL_S = 1e-5
"""Lowered from CPython's default (5ms) only for the duration of this test's own
race, and always restored in a `finally`: the default interval is wider than this
whole battery's warm-up spawn, so without lowering it the racing thread would never
be handed the GIL inside the race window at all (measured; see the module
docstring). Left at the default for every other test in this process (pytest runs
the whole e2e suite in one process), since leaking a lowered interval into later,
unrelated tests would be a timing hazard of this test's own making.
"""

_RACE_FRACTIONS = (0.05, 0.1, 0.2, 0.3)
"""Delays for the racing thread, each a fraction of this run's own measured warm-up
spawn duration rather than a fixed number of seconds: the fallback scan's own cost
scales with how many fds this host and this run happen to have open, so a fraction
of a locally measured baseline lands in the race window on a slower or faster host
alike, where a hardcoded millisecond figure would not. Measured on this host: the
window these fractions target runs from about 5% to 30% of that baseline; past
roughly 40% the fork has already happened and the race can no longer bite (module
docstring).
"""

_RACE_ITERATIONS_PER_FRACTION = 8
"""Enough repeats per fraction for a flaky miss on one iteration not to hide a
regression, without growing this battery past a fraction of a second: the fallback
scan this race needs is already the slow path (`_FD_SCAN_CAP`'s own docstring), so
every iteration here pays that cost once.
"""


def _measure_warmup_spawn_duration_s() -> float:
    """Spawn and reap `true` a few times with nothing else going on, and return the
    mean wall-clock cost -- this run's own baseline for `_RACE_FRACTIONS` to scale
    against, since the fallback scan's own cost is this host's to measure, not this
    test's to assume.
    """
    durations: list[float] = []
    for _ in range(5):
        start = time.perf_counter()
        process = spawn(("true",), _STDIO_FDS)
        reap(process.pid)
        durations.append(time.perf_counter() - start)
    return sum(durations) / len(durations)


def _spawn_true_racing_a_close_of_one_planted_fd(delay_s: float) -> int | ProcessUnknown:
    """Plant an inheritable pipe fd outside `spawn`'s allow-list, start a thread
    that closes it after `delay_s`, and run `spawn(("true",), _STDIO_FDS)` against
    that race.

    Returns the reaped exit code on success. Lets `SpawnError` propagate rather
    than catching it here: the one call site below is where AC#2's assertion
    belongs, not buried in this helper.
    """
    planted_read_fd, planted_write_fd = os.pipe()
    os.close(planted_write_fd)
    os.set_inheritable(planted_read_fd, True)

    def close_the_planted_fd_after_a_delay() -> None:
        time.sleep(delay_s)
        try:
            os.close(planted_read_fd)
        except OSError:
            pass  # already closed by this test's own cleanup below; not a failure

    racer = threading.Thread(target=close_the_planted_fd_after_a_delay)
    racer.start()
    try:
        process = spawn(("true",), _STDIO_FDS)
        return reap(process.pid)
    finally:
        racer.join()
        try:
            os.close(planted_read_fd)
        except OSError:
            pass  # the race, or the spawned process's own close action, got it first


@pytest.mark.skipif(
    # Whether `_open_inheritable_fds` (TASK-0001.05) will list `/proc/self/fd`
    # rather than fall back to probing -- the one fact this battery's plantability
    # depends on, named here rather than through `sys.platform` for the same reason
    # `spawn`'s own `setsid` choice is (TASK-0001.12 review): it is the measured
    # presence of a path, not an assumption about which OS has one. Checked inline
    # (not through a named helper) because a project function called at import
    # time, even a pure one, is what `import-time-side-effects` flags; a direct
    # stdlib call in the decorator itself, like the existing `shutil.which(...) is
    # None` skips elsewhere in this suite, is not.
    os.path.isdir("/proc/self/fd"),
    reason=(
        "this race is plantable via Python threading only on the fallback probe-loop "
        "scan path (no /proc/self/fd here to list); measured unplantable the same way "
        "on the /proc path (this module's own docstring carries the counts) -- reported "
        "as not run here rather than passed vacuously (decision-0001's e2e rule)"
    ),
)
def test_spawn_recovers_when_another_thread_closes_a_close_action_fd_first() -> None:
    """TASK-0001.09 AC#2: with the real race planted against `spawn` -- a genuine
    second thread, nothing patched or faked -- `spawn` no longer fails a spawn that
    would otherwise have succeeded, across every delay this run's own baseline
    says should land inside the window.

    Each outcome is checked twice: `spawn` itself must not raise `SpawnError`
    (the regression AC#2 is about), and the process it started must actually have
    run `true` to a clean exit (0) -- so a vacuous pass (the race missing the
    window every time, this assertion trivially true either way) is ruled out by
    the differential recorded in this task's implementation notes, not by this
    assertion alone.
    """
    old_switch_interval = sys.getswitchinterval()
    sys.setswitchinterval(_RACE_SWITCH_INTERVAL_S)
    try:
        baseline_s = _measure_warmup_spawn_duration_s()
        for fraction in _RACE_FRACTIONS:
            delay_s = fraction * baseline_s
            for _ in range(_RACE_ITERATIONS_PER_FRACTION):
                try:
                    exit_code = _spawn_true_racing_a_close_of_one_planted_fd(delay_s)
                except SpawnError as exc:
                    pytest.fail(
                        f"spawn raised {exc!r} at delay_s={delay_s!r} "
                        f"(fraction={fraction!r} of baseline_s={baseline_s!r}): "
                        "the close-action race was not recovered"
                    )
                assert exit_code == 0
    finally:
        sys.setswitchinterval(old_switch_interval)
