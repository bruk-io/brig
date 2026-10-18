"""E2E battery for the TIOCSTI confinement hole (TASK-0001.05 AC#2, AC#3).

TIOCSTI is a legacy terminal ioctl that queues a keystroke for the terminal to
process. A process sharing a controlling terminal with something outside a jail can,
without its session detached from that terminal, use TIOCSTI to inject keystrokes the
owner of that terminal will execute next -- an escape that bypasses every other
boundary the jail states.

This file has four batteries, each guarded by a kernel-availability check that is
itself the positive control (rule 11): if TIOCSTI is not compiled in on this kernel
(``CONFIG_LEGACY_TIOCSTI=n``) or disabled at runtime (``dev.tty.legacy_tiocsti=0``),
every injection attempt below fails with ``EIO`` regardless of confinement, and a
battery that could not tell a denied injection from an unavailable ioctl would be
reporting nothing -- so each battery below checks this first and skips, with that
measured fact as its reason, rather than ever asserting on an ambiguous result.

Earlier revision: this file guarded every test on ``os.isatty(0)``, which is false
under pytest's own capture and in CI with no terminal attached, so neither test ever
ran anywhere (rule 11's hole the review named). This revision manufactures its own
controlling terminal with ``pty.fork()`` instead of depending on the one the test
process happens to have, so no battery below ever skips for lack of a terminal; the
real-jail battery still skips where bwrap itself is not installed (macOS), the same
as every other bwrap test in this suite. A keystroke injected during the battery
lands only on this freshly made pty, never on the operator's own terminal.

- ``test_positive_control_...``: TIOCSTI succeeds against a terminal a process still
  owns as its own controlling terminal (no confinement at all) -- proof the ioctl
  exists on this kernel and this probe can see it succeed, so a later "denied" result
  is evidence of something closing the hole, not an artifact of a probe that could
  never have detected it open. Runs everywhere; no bwrap needed.
- ``test_tiocsti_injection_fails_once_infra_detaches_the_session``: the gateway half,
  against `brig.infra.processes.spawn` directly (decision-0001 rule 4 lets an e2e test
  import one `brig.infra` module for exactly this). Where `spawn` can ask for
  `setsid=True`, it detaches the spawned process's session before anything else runs,
  which on its own already closes this hole -- independently of any jail type's flags.
  Needs no bwrap, but it does need that flag, which is not on every interpreter
  (TASK-0001.12): where `SpawnedProcess.session_detached` comes back `False` this skips
  with that measurement as the reason, because infra makes no claim there for it to
  grade -- the closure is then the jail type's, which the bwrap battery below grades.
- ``test_tiocsti_injection_fails_in_a_real_bwrap_jail``: the same probe run as a real
  bwrap jail's one process, through the public API. Guarded to skip cleanly where
  bwrap is not installed (macOS); runs for real in CI on Linux.
- ``test_new_session_is_the_sole_closer_of_tiocsti_when_infra_detaches_no_session``:
  TASK-0001.11's differential, grading the attribution itself rather than only the
  end-to-end property. Runs the probe through brig's real bwrap argv and, built
  locally here (never by changing production code -- see
  ``_BWRAP_ARGV_WITHOUT_NEW_SESSION``'s own docstring), the same argv with
  ``--new-session`` removed, both directly through ``brig.infra.processes.spawn``.

AC#2 asks that bwrap's `--new-session` close this hole "and not infra's setsid". This
task's review originally measured `brig.infra.processes.spawn` setting `setsid=True`
unconditionally, before bwrap's own argv is ever parsed, and concluded no black-box
probe could ever attribute the closure to one layer over the other -- the weaker of
the two always ran first and already sufficed.

TASK-0001.12 narrowed that: `setsid=True` is compiled out of uv's managed CPython, the
build this project's own CI uses, so there `spawn` gets a new process group only, the
controlling terminal stays shared, and `--new-session` is the one thing closing the
hole. The attribution is therefore not uniformly ungradable -- it depends on a property
infra now reports, `SpawnedProcess.session_detached`. Where that is `False` (this
project's own CI toolchain), the fourth battery above grades the attribution directly:
it runs brig's real argv and the same argv with only `--new-session` stripped, and
requires the first denied and the second to inject, so a change that weakened or
dropped the flag would show up as this test injecting, not merely as the end-to-end
battery continuing to pass for a different reason. Where `session_detached` is `True`
(macOS), the attribution remains exactly as ungradable as TASK-0001.05's review
described -- infra's own session detachment already closes the hole first and that
battery skips, with the measurement as its reason, rather than asserting on a result
that would prove nothing. `domain/jail_types/bwrap.py`'s own docstring carries the full
attribution in prose either way.
"""

import errno
import fcntl
import os
import pty
import shutil
import sys
import termios
import threading
from collections.abc import Callable

import pytest

from brig import create_bwrap_jail, destroy_jail, run_jail
from brig.infra.processes import ProcessUnknown, reap, spawn

_ERRNO_EXIT_OFFSET = 100
"""Offsets a denied probe's errno into its exit code, so the result never collides
with the exit codes an unrelated failure gives instead -- `python` missing, a bad
`-c` string, bwrap itself failing to start -- which land under 128 but at their own,
unoffset values (1, 2, 126, 127). An exit code outside `[_ERRNO_EXIT_OFFSET,
_ERRNO_EXIT_OFFSET + 255]` is therefore never mistaken for "the ioctl ran and was
denied with this errno": it is evidence the probe never got that far.
"""

_TIOCSTI_PROBE = f"""
import fcntl, sys, termios
try:
    fcntl.ioctl(0, termios.TIOCSTI, b"x")
    sys.exit(0)
except OSError as exc:
    sys.exit({_ERRNO_EXIT_OFFSET} + (exc.errno or 0))
"""
"""The probe command, run as `python -c <this>`: attempts to inject a keystroke with
TIOCSTI on fd 0 and exits with 0 (injection succeeded -- confinement failed) or
`_ERRNO_EXIT_OFFSET` plus the ioctl's own errno (injection denied). Reports through
its exit code alone, never a pipe: a real bwrap jail's allow-list
(`domain/jail_types/bwrap.py`'s `_INHERITABLE_FDS`) carries only 0/1/2, the same
discipline the sibling fd battery's `_FSTAT_PROBE` uses for the same reason.
"""

_PROBE_CRASHED_EXIT_CODE = 99
"""What `_run_in_pty_session` reports if `child` raised instead of returning a plain
exit code -- `create_bwrap_jail` raising `JailSpawnFailed`, say, or `_reap_exit_code`
raising its own `AssertionError`. Outside `_ERRNO_EXIT_OFFSET`'s whole band (100-355,
clamped to the 0-255 a process exit code can hold), so it is never mistaken for a
denied ioctl's own encoded errno -- it means the probe never got that far at all.
"""

_DENIED_ERRNO = errno.EPERM if sys.platform == "linux" else errno.EACCES
"""The errno a denied TIOCSTI ioctl reports once the caller is not the terminal's
controlling process and lacks `CAP_SYS_ADMIN`: `EPERM` on Linux (this task's review
measured it there). This host's own kernel (Darwin) reports `EACCES` for the same
denial instead -- measured directly against `brig.infra.processes.spawn` while writing
this battery. Only the gateway battery below needs this platform split: the real-jail
battery only ever runs on Linux, since bwrap is Linux-only.
"""


_BWRAP_ARGV_PREFIX: tuple[str, ...] = (
    "bwrap",
    "--ro-bind",
    "/",
    "/",
    "--unshare-all",
    "--die-with-parent",
    "--new-session",
    "--",
)
"""Mirrors `domain/jail_types/bwrap.py`'s own `_BWRAP_ARGV`, kept as a local copy
rather than an import: decision-0001 rule 4 lets an e2e test import the public API,
or one `brig.infra` module for a gateway test, never a `domain` module directly, and
this differential needs a variant `compile_run` itself deliberately never produces
(the same argv with `--new-session` stripped), which only exists by building it here,
locally, rather than by changing production code. There is also no public entry point
that would hand back a compiled `Plan`'s argv instead: `create_bwrap_jail` compiles
and starts the process in the same call and returns neither (checked --
`presentation/api.py` and `brig/__init__.py` name nothing that returns a `Plan`), so
this is the only way to get at these flags from `tests/e2e/` at all, not a shortcut
taken over an available public one.

The cost of the copy is real and not hidden: if `_BWRAP_ARGV` ever changes, this
constant has to change with it by hand, and nothing in this suite catches that drift
mechanically -- it is a maintenance obligation on whoever next edits
`domain/jail_types/bwrap.py`, not a gap any other test here closes.
"""

_BWRAP_ARGV_WITHOUT_NEW_SESSION: tuple[str, ...] = tuple(
    flag for flag in _BWRAP_ARGV_PREFIX if flag != "--new-session"
)
"""The same prefix with `--new-session` removed -- derived from the one literal above
by filtering, rather than retyped as a second literal, so the two can only ever differ
by that one flag. That is the entire point of a differential: TASK-0001.12 measured
this by hand (positive control injects; the real argv is denied; this argv injects
again) and this is that same negative half, committed for real.
"""


def _bwrap_differential_probe(argv_prefix: tuple[str, ...]) -> Callable[[], int]:
    """Build the child `_run_in_pty_session` runs for one half of the TASK-0001.11
    differential: spawn the TIOCSTI probe directly behind `argv_prefix` through
    `brig.infra.processes.spawn` -- the same call `_spawned_tiocsti_probe` uses, and
    the same one every jail type's own driver uses underneath the public API --
    inheriting fd 0 (this process's own pty slave) and nothing else.
    """

    def probe() -> int:
        process = spawn((*argv_prefix, sys.executable, "-c", _TIOCSTI_PROBE), (0, 1, 2))
        return _reap_exit_code(process.pid)

    return probe


def _drain_until_closed(fd: int) -> None:
    """Discard everything `fd` carries until it closes.

    Runs on its own thread for the lifetime of every `_run_in_pty_session` call below:
    a pty's input queue is bounded, and nothing reads the master end the way a real
    shell would, so a probe that writes anything to the stdout or stderr it shares
    with the pty's slave could otherwise block on a full buffer forever.
    """
    while True:
        try:
            if not os.read(fd, 4096):
                return
        except OSError:
            return


def _run_in_pty_session(child: Callable[[], int]) -> int:
    """Fork a process that owns a freshly made pty as its own controlling terminal,
    run `child` inside it, and return its exit code.

    `pty.fork()` does the `setsid` and `TIOCSCTTY` work itself and dup's the pty's
    slave onto fd 0/1/2 of the forked process -- exactly the shape TIOCSTI's hole is
    about: a process with a real controlling terminal, the way an interactive shell
    has one. The pty is made fresh for this one call and nothing else ever reads its
    master end as a shell would, so an injected keystroke here never reaches the
    operator's own terminal, another test, or anything outside this one call.

    `child` runs inside the forked process and must not return to pytest: this
    function calls it only through `os._exit`, so no pytest or interpreter teardown
    code the parent still has outstanding ever runs a second time in the child. An
    exception `child` raises instead of returning is caught here and turned into
    `_PROBE_CRASHED_EXIT_CODE` for the same reason: left to propagate, it would run
    pytest's own teardown inside this forked, already-diverged process, print a
    second, misleading traceback, and leave the parent asserting on whatever
    arbitrary exit code that teardown happened to produce instead of the probe's
    own protocol (plain exit codes, pinned to a known range -- see
    `_ERRNO_EXIT_OFFSET`).
    """
    pid, master_fd = pty.fork()
    if pid == 0:
        try:
            os._exit(child())
        except BaseException:
            os._exit(_PROBE_CRASHED_EXIT_CODE)
    reader = threading.Thread(target=_drain_until_closed, args=(master_fd,), daemon=True)
    reader.start()
    try:
        _, status = os.waitpid(pid, 0)
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
    return os.waitstatus_to_exitcode(status)


def _reap_exit_code(pid: int) -> int:
    """Reap `pid`, this probe's own spawned child, and return its exit code.

    Raises:
        AssertionError: `pid` was no longer this process's child to wait for by the
            time this ran -- something else collected it first. The probe's protocol
            is plain exit codes; there is no such code to fall back to here, so this
            fails loudly rather than reporting a result the probe never produced.
    """
    outcome = reap(pid)
    if isinstance(outcome, ProcessUnknown):
        raise AssertionError(f"pid {pid} was reaped by something else before this probe could be")
    return outcome


def _unconfined_tiocsti_probe() -> int:
    """The child `_run_in_pty_session` runs for the kernel-availability check and the
    positive control: attempt TIOCSTI injection on fd 0 while this process still owns
    the pty as its own controlling terminal -- the ordinary, unconfined case.
    """
    try:
        fcntl.ioctl(0, termios.TIOCSTI, b"x")
        return 0
    except OSError as exc:
        return _ERRNO_EXIT_OFFSET + (exc.errno or 0)


def _spawned_tiocsti_probe() -> int:
    """The child `_run_in_pty_session` runs for the gateway battery: spawn the
    TIOCSTI probe through `brig.infra.processes.spawn` -- the same call every jail
    type's driver uses -- inheriting fd 0 (this process's own pty slave) and nothing
    else, and report what the spawned process saw.
    """
    process = spawn((sys.executable, "-c", _TIOCSTI_PROBE), (0, 1, 2))
    return _reap_exit_code(process.pid)


def _jailed_tiocsti_probe() -> int:
    """The child `_run_in_pty_session` runs for the real-jail battery: run the same
    probe as a real bwrap jail's one process, through the public API, inheriting
    fd 0 the same way (bwrap's own stated allow-list also carries 0/1/2).
    """
    jail = create_bwrap_jail((sys.executable, "-c", _TIOCSTI_PROBE))
    exit_code = run_jail(jail)
    destroy_jail(jail)
    return exit_code


def _skip_if_infra_cannot_detach_a_session() -> None:
    """Spawn one trivial process through `brig.infra.processes.spawn` and skip the
    calling test -- with that measurement as the reason -- if `session_detached` comes
    back `False`.

    Asks `spawn` itself rather than checking `sys.platform` or probing
    `os.posix_spawn` here, because the answer is a property of how this interpreter was
    built, not of the OS (TASK-0001.12), and because what the skipped test grades is
    infra's claim: the thing to measure is therefore the claim, from the same call the
    test would use. Reaped immediately, so this leaves no child behind.
    """
    process = spawn(("true",), (0, 1, 2))
    detached = process.session_detached
    reap(process.pid)
    if not detached:
        pytest.skip(
            "this interpreter has no posix_spawn setsid flag, so infra spawns a new "
            "process group only and detaches no session to grade"
        )


def _skip_unless_new_sessions_closure_is_attributable() -> None:
    """Spawn one trivial process through `brig.infra.processes.spawn` and skip the
    calling test -- with that measurement as the reason -- unless `session_detached`
    comes back `False`.

    The inverse guard of `_skip_if_infra_cannot_detach_a_session`: where infra already
    detaches a session, that alone already closes TIOCSTI before bwrap's own argv is
    ever parsed (TASK-0001.05's review measured exactly this), so both halves of the
    TASK-0001.11 differential would come back denied for infra's own reason and the
    test would prove nothing about `--new-session` specifically. Reaped immediately,
    so this leaves no child behind, the same as its counterpart.
    """
    process = spawn(("true",), (0, 1, 2))
    detached = process.session_detached
    reap(process.pid)
    if detached:
        pytest.skip(
            "this interpreter's spawn detaches a session (session_detached=True), so "
            "infra's own setsid already closes TIOCSTI before bwrap's argv is parsed "
            "and --new-session's own contribution cannot be isolated here -- see "
            "TASK-0001.12's attribution measurement"
        )


def _skip_if_tiocsti_unavailable() -> None:
    """Run the unconfined probe once, and skip the calling test -- with that
    measurement as the reason -- if it reports TIOCSTI is not available on this
    kernel at all, rather than letting a later assert read a denial that never
    happened as a pass.
    """
    availability = _run_in_pty_session(_unconfined_tiocsti_probe)
    if availability == _ERRNO_EXIT_OFFSET + errno.EIO:
        pytest.skip("TIOCSTI is disabled on this kernel (CONFIG_LEGACY_TIOCSTI=n)")


def test_positive_control_tiocsti_succeeds_against_an_owned_controlling_terminal() -> None:
    """Rule 11's positive control: TIOCSTI injection against a terminal a process
    still owns as its own controlling terminal succeeds -- proof the ioctl exists on
    this kernel and this probe can see it succeed, so the batteries below reporting a
    denial is evidence something closed the hole, not an artifact of a probe that
    could never have detected it open.
    """
    exit_code = _run_in_pty_session(_unconfined_tiocsti_probe)
    if exit_code == _ERRNO_EXIT_OFFSET + errno.EIO:
        pytest.skip("TIOCSTI is disabled on this kernel (CONFIG_LEGACY_TIOCSTI=n)")
    assert exit_code == 0


def test_tiocsti_injection_fails_once_infra_detaches_the_session() -> None:
    """The gateway half of AC#2/AC#3's TIOCSTI battery, against
    `brig.infra.processes.spawn` directly: a process it starts, sharing fd 0 (and so
    the pty device) with the process that spawned it, cannot inject through TIOCSTI,
    because `spawn`'s own `setsid=True` detaches its session before the probe ever
    runs. Needs no bwrap, and pins the exact errno `fcntl.ioctl` reports, so no other
    `OSError` (a missing module, a bad fd) can masquerade as a denied injection.

    Skips where this interpreter has no `setsid` flag for `spawn` to use
    (TASK-0001.12): infra then detaches no session and makes no claim here to grade.
    """
    _skip_if_infra_cannot_detach_a_session()
    _skip_if_tiocsti_unavailable()
    exit_code = _run_in_pty_session(_spawned_tiocsti_probe)
    assert exit_code == _ERRNO_EXIT_OFFSET + _DENIED_ERRNO


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_tiocsti_injection_fails_in_a_real_bwrap_jail() -> None:
    """The claim AC#2 states for the bwrap jail type specifically, graded for real
    through the public API (`create_bwrap_jail`/`run_jail`): the same probe, run as a
    real bwrap jail's one process, cannot inject through TIOCSTI either. Pins the
    exact errno for the same reason the gateway battery above does.

    What this does not grade -- that `--new-session` itself, rather than infra's own
    `setsid=True`, is what closes the hole -- is this file's module docstring.
    """
    _skip_if_tiocsti_unavailable()
    exit_code = _run_in_pty_session(_jailed_tiocsti_probe)
    assert exit_code == _ERRNO_EXIT_OFFSET + _DENIED_ERRNO


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_new_session_is_the_sole_closer_of_tiocsti_when_infra_detaches_no_session() -> None:
    """TASK-0001.11: the differential TASK-0001.12 measured by hand, committed as a
    real, repeatable test. Runs brig's real bwrap argv (with `--new-session`) and the
    same argv with only that flag removed, both directly through
    `brig.infra.processes.spawn` -- the same call `presentation/drivers/bwrap.py`'s
    own `run` performs underneath the public API -- under `session_detached=False`:
    the toolchain this project's own CI runs. The first must be denied and the second
    must inject; that is what makes `--new-session` attributable as the hole's sole
    closer there, rather than merely present alongside a session detachment infra
    cannot actually provide on this toolchain (TASK-0001.12).

    Skips wherever the differential cannot mean anything: no bwrap installed, this
    interpreter's own `spawn` already detaches a session and so already closes the
    hole before bwrap's argv is ever parsed, or TIOCSTI is unavailable on this kernel.
    """
    _skip_unless_new_sessions_closure_is_attributable()
    _skip_if_tiocsti_unavailable()

    with_new_session = _run_in_pty_session(_bwrap_differential_probe(_BWRAP_ARGV_PREFIX))
    assert with_new_session == _ERRNO_EXIT_OFFSET + _DENIED_ERRNO

    without_new_session = _run_in_pty_session(
        _bwrap_differential_probe(_BWRAP_ARGV_WITHOUT_NEW_SESSION)
    )
    assert without_new_session == 0
