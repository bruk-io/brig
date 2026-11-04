"""E2E gateway test for `brig.infra.processes`, against the real OS (decision-0001 rule 4): the
`ECHILD` race (`reap` and `peek` return `ProcessUnknown`, never a raw `ChildProcessError`),
`peek` and `release` (decision-0003), and `destroy_jail` over a real process group
(TASK-0001.08).

`Jail.process` takes a real spawned process and `Jail.supervisors` a real `LiveSupervisor`,
each through `cast`: this layer may not import the domain or presentation types they stand for,
and the driver reads only `.pid` and `.pgid`. The `LiveSupervisor` is never started; its
`close` on a pid it does not hold is the real no-op.
"""

import errno
import os
import shutil
import signal
import tempfile
import time
from typing import Any, cast

import pytest

from brig import Jail, JailTeardownFailed, destroy_jail
from brig.infra.processes import (
    ProcessUnknown,
    SpawnError,
    group_alive,
    peek,
    reap,
    release,
    spawn,
)
from brig.infra.supervisor.link import LiveSupervisor

_STDIO_FDS = (0, 1, 2)
"""The allow-list these tests pass `spawn`: the standard streams only."""

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

_LEADER_EXITS_BEFORE_GROUP_NO_PRE_SLEEP_ITERATIONS = 40
"""Lower than `_LEADER_EXITS_BEFORE_GROUP_ITERATIONS` on purpose: on Linux this shape's
race is near-deterministic with `kill_grace_s=0.0` (40 of 40 on native Linux, and 200 of
200 in `brig-probe-amd64:latest`; the test's own docstring names each figure's host and
method), so a far smaller count is already decisive there. Running 150 of these would not
buy more confidence, only a longer e2e suite.
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
    (`destroy_jail`'s default `kill_grace_s`), so this loop no longer tolerates
    `JailTeardownFailed` either.

    Which test catches a regression of that fix depends on the host (TASK-0051). On
    native Linux the one that discriminates is the no-pre-sleep variant below (40 of
    40 there, 2026-11-04); this test's power depends on the host, from 0 to 4 in 150
    on that native Linux host (0 to 3 in its lead's runs) to 150 of 150 under
    emulation and on macOS, so keep both. Each figure counts `JailTeardownFailed` in
    one run of this test with the grace window off (`kill_grace_s=0.0`) unless it
    says the real default. The method, where a figure says "forced": the test
    unmodified, `brig.destroy_jail.__kwdefaults__["kill_grace_s"]` set to 0.0 before
    it runs; a figure without it records only that the window was 0.0.

    - Native Linux, 2026-11-04: an x86_64 Firecracker microVM under KVM (hardware
      virtualisation, no CPU emulation), 4 vCPUs, kernel 6.18.44-fc-v233, Ubuntu
      24.04 userland in a container, Python 3.15.0b4, the host shared with other
      work. 0, 1 and 3 of 150 in three runs (TASK-0051's lead); forced, 0, 2 and 4
      of 150 in three more, and 0 of 150 in three runs against the real default
      (TASK-0051's worker).
    - `brig-probe-amd64:latest` (privileged, `--platform linux/amd64`) on a Darwin
      27 host, the amd64 image emulated, its Linux kernel not recorded. Forced: 150
      of 150, twice (TASK-0017's reviewer).
    - `brig-probe-amd64:latest` (privileged), host, kernel and emulation not
      recorded: 0 of 150, and 0 of 150 against the real default (TASK-0017's
      description, from TASK-0013's review). Near the native Linux figures above,
      far from the emulated ones on the same image.
    - Native macOS, Darwin 27, no emulation, its kernel build not recorded: 149 of
      150 (as first recorded in this docstring, its run not on the board), 145 of
      150 and 0 of 150 against the real default (TASK-0017's description), and,
      forced, 150 of 150 (TASK-0017's reviewer).

    As measured, the race fires through the 0.05s pre-sleep between spawning the
    leader and calling `destroy_jail` on macOS and under emulation, and seldom on
    native Linux, where the leader has usually exited and its orphaned sibling
    settled by the time `destroy_jail` looks.
    """
    escaped: list[BaseException] = []
    teardown_failed = 0

    for _ in range(_LEADER_EXITS_BEFORE_GROUP_ITERATIONS):
        spawned = spawn(_LEADER_EXITS_BEFORE_GROUP_ARGV, _STDIO_FDS)
        time.sleep(0.05)
        jail = Jail(process=cast(Any, spawned), supervisors=cast(Any, LiveSupervisor(())))
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


def test_destroy_jail_survives_the_leader_exiting_before_its_group_without_a_pre_sleep() -> None:
    """TASK-0017: the test above without its 0.05s pre-sleep, calling `destroy_jail`
    the instant after spawning, while the leader may still be exiting and its sibling
    still forking, which is exactly when the post-KILL verify can still see a group
    mid-death.

    On native Linux this is the test that discriminates a regression of
    TASK-0001.07's fix (TASK-0051): 40 of 40 there, where the pre-sleep test above
    caught 0 to 4 in 150 on the same host. Keep it; the pre-sleep test's power
    depends on the host. Each figure counts `JailTeardownFailed` in one run of this
    test with the grace window off (`kill_grace_s=0.0`) unless it says the real
    default, by the method the test above names ("forced" where it was used).

    - Native Linux, 2026-11-04: the Firecracker microVM the test above names (x86_64
      under KVM, no CPU emulation, 4 vCPUs, kernel 6.18.44-fc-v233, Ubuntu 24.04
      userland in a container, Python 3.15.0b4, shared with other work). 40 of 40
      (TASK-0051's lead); forced, 38, 40, 40 and 40 of 40 in four runs, and 0 of 40
      in three runs against the real default (TASK-0051's worker).
    - `brig-probe-amd64:latest` (privileged, `--platform linux/amd64`) on a Darwin
      27 host, the amd64 image emulated, its Linux kernel not recorded. Forced: 39
      of 40 (TASK-0017's reviewer).
    - `brig-probe-amd64:latest` (privileged), host, kernel and emulation not
      recorded: 200 of 200, and 0 of 200 against the real default, at 200
      iterations (TASK-0017's description, from TASK-0013's review).
    - Native macOS, Darwin 27, no emulation, its kernel build not recorded: weak and
      noisy, 2% to 34% of 150 across several runs, and 0 of 150 against the real
      default across several runs (TASK-0017's implementer, as reported); forced, 2
      of 40 (TASK-0017's reviewer). There the leader typically finishes exiting and
      forking its sibling before this process is scheduled back in, so this test
      leans on Linux for discrimination and the pre-sleep test on macOS. What it
      confirms on macOS is that dropping the pre-sleep adds no flakiness against
      the real default.
    """
    escaped: list[BaseException] = []
    teardown_failed = 0

    for _ in range(_LEADER_EXITS_BEFORE_GROUP_NO_PRE_SLEEP_ITERATIONS):
        spawned = spawn(_LEADER_EXITS_BEFORE_GROUP_ARGV, _STDIO_FDS)
        jail = Jail(process=cast(Any, spawned), supervisors=cast(Any, LiveSupervisor(())))
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
    jail = Jail(process=cast(Any, spawned), supervisors=cast(Any, LiveSupervisor(())))

    started = time.monotonic()
    destroy_jail(jail, kill_grace_s=5.0)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, (
        f"destroy_jail took {elapsed:.2f}s -- a misread zombie-as-alive would "
        "escalate signals for nothing and burn the whole 5s grace window"
    )


def test_spawn_raises_spawnerror_for_an_unresolvable_bare_name() -> None:
    """TASK-0014: `spawn`'s own pre-check now raises `SpawnError` for a bare
    `argv[0]` that cannot be resolved against `PATH`, on every platform --
    previously only macOS's own `posix_spawnp` raised for this; on Linux, glibc
    returned a healthy-looking spawned process whose child just exited 127.
    """
    with pytest.raises(SpawnError) as excinfo:
        spawn(("definitely-not-a-real-command-xyz",), _STDIO_FDS)

    assert excinfo.value.errno == errno.ENOENT


def test_spawn_resolvable_bare_name_is_unaffected_by_the_pre_check() -> None:
    """A bare `argv[0]` that resolves against `PATH` still spawns normally --
    the pre-check adds a raise for the unresolvable case, nothing else.
    """
    process = spawn(("true",), _STDIO_FDS)

    assert reap(process.pid) == 0


def test_spawn_direct_path_is_checked_literally_but_still_checked() -> None:
    """A direct path (one containing `/`) is checked literally by `shutil.which`,
    never PATH-searched -- matching `execvp`'s own semantics -- so an existing
    one still spawns. A missing one raising `SpawnError` is NOT pre-existing
    OS-level behavior on every platform: on macOS the OS itself already raised
    for this shape, but on Linux `os.posix_spawnp` with a nonexistent direct
    path does not raise either (measured: the identical unexplained-exit-127
    shape a missing bare name has) -- this pre-check is what makes it raise
    there too, the same narrowing TASK-0014 was filed to add for bare names.
    """
    existing = shutil.which("true")
    assert existing is not None

    process = spawn((existing,), _STDIO_FDS)
    assert reap(process.pid) == 0

    with pytest.raises(SpawnError):
        spawn(("/definitely/not/a/real/path/brig-test-xyz",), _STDIO_FDS)


def test_spawn_pre_check_ignores_envs_own_narrower_path() -> None:
    """A narrow `PATH` given only through `env` must NOT make the pre-check raise
    for a name that resolves through this process's own `os.environ`: measured
    directly (Apple libc and glibc both), `posix_spawnp`'s own PATH search
    consults the calling process's real environment, never `env`'s, so a bare
    name on this process's own `PATH` spawns fine regardless of what `env` says.
    A wrong implementation that searched `env`'s own `PATH` instead would raise
    `SpawnError` here even though the real spawn below would have succeeded.
    """
    narrow_env = {"PATH": "/definitely/not/a/real/directory"}

    process = spawn(("true",), _STDIO_FDS, env=narrow_env)

    assert reap(process.pid) == 0


def test_spawn_pre_check_raises_for_a_name_only_envs_own_path_would_resolve() -> None:
    """The case this task was actually filed for, reproduced through `env`: a
    bare name resolvable only through a `PATH` given in `env`, not through this
    process's own `os.environ`, must raise `SpawnError` -- because the real
    `posix_spawnp` below never consults `env`'s own `PATH` for its search
    either, and would otherwise spawn a child that exits 127 unexplained
    (measured directly: this exact shape, on Linux/glibc in
    brig-probe-amd64:latest, before this pre-check existed).
    """
    bin_dir = tempfile.mkdtemp()
    script_path = os.path.join(bin_dir, "brig-test-precheck-probe")
    with open(script_path, "w") as handle:
        handle.write("#!/bin/sh\nexit 0\n")
    os.chmod(script_path, 0o755)
    try:
        with pytest.raises(SpawnError):
            spawn(("brig-test-precheck-probe",), _STDIO_FDS, env={"PATH": bin_dir})
    finally:
        os.remove(script_path)
        os.rmdir(bin_dir)


def _write_fake_proc_entry(proc_root: str, pid: int, stat_content: str) -> None:
    """Write `stat_content` verbatim to a `<proc_root>/<pid>/stat` this test builds
    by hand -- a real file on a real filesystem, not a patched `open`, standing in
    for a `/proc` entry whose content a real kernel never actually writes (TASK-
    0016): `group_alive`'s own `proc_root` parameter exists so this shape can be
    proven with real I/O rather than faked.
    """
    entry_dir = os.path.join(proc_root, str(pid))
    os.mkdir(entry_dir)
    with open(os.path.join(entry_dir, "stat"), "w") as handle:
        handle.write(stat_content)


def test_group_alive_tolerates_a_malformed_or_truncated_stat_line() -> None:
    """TASK-0016 AC#1/#2: a malformed `/proc/<pid>/stat` line -- empty, missing
    its `)` entirely, or with too few fields after it -- is skipped like a
    vanished entry already was, never raised out of `group_alive` as a plain
    `IndexError`/`ValueError`.

    `held` must be non-empty to take the Linux scan branch at all (`group_alive`'s
    own docstring); `0` names no entry this test ever writes, so nothing here is
    excluded by it.

    Pre-fix, this fails with a raw `IndexError` (the empty-content and too-few-
    fields entries, where `fields[0]` or `fields[2]` has nothing to read) or
    `ValueError` (the no-`)` entry, whose third field is not an int) -- confirmed
    by running this test against the pre-fix code before the fix was written.
    """
    fake_proc = tempfile.mkdtemp()
    try:
        _write_fake_proc_entry(fake_proc, 1, "")
        _write_fake_proc_entry(fake_proc, 2, "not a real stat line at all")
        _write_fake_proc_entry(fake_proc, 3, "123 (prog) S 1")

        result = group_alive(999_999, held=frozenset({0}), proc_root=fake_proc)

        assert result is False
    finally:
        shutil.rmtree(fake_proc)


def test_group_alive_still_finds_a_well_formed_match_past_malformed_entries() -> None:
    """The fix's own risk (the plan's own words): widening what is tolerated must
    not swallow a genuinely alive, well-formed entry elsewhere in the scan. A real
    match sits alongside the same three malformed entries above, and is still
    found.
    """
    fake_proc = tempfile.mkdtemp()
    try:
        _write_fake_proc_entry(fake_proc, 1, "")
        _write_fake_proc_entry(fake_proc, 2, "not a real stat line at all")
        _write_fake_proc_entry(fake_proc, 3, "123 (prog) S 1")
        _write_fake_proc_entry(fake_proc, 4, "4 (real) R 1 42 42")

        result = group_alive(42, held=frozenset({0}), proc_root=fake_proc)

        assert result is True
    finally:
        shutil.rmtree(fake_proc)


def test_group_alive_returns_a_bool_never_raises_on_the_real_host() -> None:
    """AC#2's other half: `group_alive` itself, driven against the real host with
    `held` non-empty (the only branch that ever reaches the Linux `/proc` scan),
    still answers a plain bool -- never raises -- for a real process group.
    """
    process = spawn(("true",), _STDIO_FDS)
    try:
        result = group_alive(process.pgid, held=frozenset({process.pid}))
        assert isinstance(result, bool)
    finally:
        os.killpg(process.pgid, signal.SIGKILL)
        reap(process.pid)
