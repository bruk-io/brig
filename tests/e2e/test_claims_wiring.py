"""Wires TASK-0001.05's two existing batteries into the grading skeleton as the
first two real `Claim`s (TASK-0001.18 AC#3), each graded from evidence this file
measures itself, in-process, rather than from a battery's own pass/fail exit code.

Why not just run `test_fd_inheritance_battery.py` / `test_tiocsti_battery.py` and
read their result: pytest reports a file that skips every test in it as a pass (exit
0), and both files legitimately skip on this host (no `bwrap` on macOS; TIOCSTI's
gateway battery also needs a `setsid` flag this interpreter may not have). Feeding
that exit code to `grade` as "the violation was blocked" would grade `ENFORCED` for
a claim nothing here actually measured -- exactly the dishonesty rule 11 exists to
rule out. So each claim below is measured directly against the real thing (a real
spawn for `fd_inheritance`, a real bwrap jail for `tiocsti_closure`), producing
`Evidence` with its own `control_observed`/`violation_blocked` pair, and a battery
that cannot run on this host (no bwrap) reports no evidence at all rather than a
fabricated one -- the same "not run, never counted as a pass" discipline the
batteries this wires in already follow. The battery files stay the fuller,
authoritative proof of each hole; this file only extracts a graded `bool` from the
same kind of measurement.
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

from brig import Claim, Evidence, Grade, create_bwrap_jail, destroy_jail, grade, run_jail
from brig.infra.processes import reap, spawn

FD_INHERITANCE_CLAIM = Claim(
    name="fd_inheritance",
    description=(
        "a fd an embedder marked inheritable for its own purposes is closed before "
        "the spawned process runs, unless named on its allow-list (TASK-0001.05 AC#1)"
    ),
)

TIOCSTI_CLOSURE_CLAIM = Claim(
    name="tiocsti_closure",
    description=(
        "a real jail's one process cannot inject keystrokes onto a controlling "
        "terminal it shares with something outside the jail, through TIOCSTI "
        "(TASK-0001.05 AC#2)"
    ),
)

_PLANTED_PAYLOAD = b"claims-wiring-evidence"
"""Known bytes distinguishing "the probe read the planted fd" from any other
content the read could, in principle, return.
"""

_FD_PROBE = """
import os, sys
target_fd = int(sys.argv[1])
out_fd = int(sys.argv[2])
try:
    data = os.read(target_fd, 4096)
    report = b"READABLE:" + data
except OSError as exc:
    report = f"CLOSED:{exc.errno}".encode()
os.write(out_fd, report)
"""
"""Mirrors `test_fd_inheritance_battery.py`'s own probe: report whether the named fd
was still readable, or closed, to the fd named second.
"""


def _probe_fd_inheritance(*, plant_on_allow_list: bool) -> bytes:
    """Plant an inheritable pipe fd, spawn `_FD_PROBE` against it through
    `brig.infra.processes.spawn`, and return what it reported seeing -- `True` names
    the planted fd on the spawn's own allow-list (the positive control: the fd must
    survive); `False` leaves it off (the claim's own case: the fd must not).
    """
    planted_read_fd, planted_write_fd = os.pipe()
    report_read_fd, report_write_fd = os.pipe()
    try:
        os.write(planted_write_fd, _PLANTED_PAYLOAD)
        os.close(planted_write_fd)
        os.set_inheritable(planted_read_fd, True)
        os.set_inheritable(report_write_fd, True)

        allowed = (
            (0, 1, 2, report_write_fd, planted_read_fd)
            if plant_on_allow_list
            else (0, 1, 2, report_write_fd)
        )
        process = spawn(
            (sys.executable, "-c", _FD_PROBE, str(planted_read_fd), str(report_write_fd)),
            allowed,
        )

        os.close(report_write_fd)
        report_write_fd = -1  # closed above; the finally block must not close it again

        chunks = bytearray()
        while True:
            chunk = os.read(report_read_fd, 4096)
            if not chunk:
                break
            chunks += chunk
        reap(process.pid)
        return bytes(chunks)
    finally:
        for fd in (planted_read_fd, report_write_fd, report_read_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass


def _measure_fd_inheritance() -> Evidence:
    """Measure `FD_INHERITANCE_CLAIM` through the gateway `spawn` directly -- no
    bwrap needed, so this runs (and grades) for real on every host this suite does.
    """
    control = _probe_fd_inheritance(plant_on_allow_list=True)
    violation = _probe_fd_inheritance(plant_on_allow_list=False)
    return Evidence(
        control_observed=control == b"READABLE:" + _PLANTED_PAYLOAD,
        violation_blocked=violation == b"CLOSED:9",  # EBADF: the fd was simply gone
    )


_ERRNO_EXIT_OFFSET = 100
"""Offsets a denied probe's errno into its exit code, so the result never collides
with the exit codes an unrelated failure gives instead -- bwrap's own setup failure
(user namespaces disabled, ordinary in CI) exits 1, and a probe that crashed exits
`_PROBE_CRASHED_EXIT_CODE` -- both well outside this band. Mirrors
`test_tiocsti_battery.py`'s own constant of the same name and purpose.
"""

_PROBE_CRASHED_EXIT_CODE = 99
"""What `_run_in_pty` reports if `child` raised instead of returning a plain exit
code -- `create_bwrap_jail` raising `JailSpawnFailed`, say. Outside
`_ERRNO_EXIT_OFFSET`'s whole band, so it is never mistaken for a denied ioctl's own
encoded errno: it means the probe never got that far at all.
"""

_DENIED_ERRNO = errno.EPERM if sys.platform == "linux" else errno.EACCES
"""The errno a denied TIOCSTI ioctl reports once the caller is not the terminal's
controlling process and lacks `CAP_SYS_ADMIN` -- `EPERM` on Linux, `EACCES` on this
host's own kernel (Darwin). Mirrors `test_tiocsti_battery.py`'s own constant; only
the real-jail probe below uses it, and that probe only ever runs on Linux, since
bwrap is Linux-only.
"""

_TIOCSTI_PROBE = f"""
import fcntl, sys, termios
try:
    fcntl.ioctl(0, termios.TIOCSTI, b"x")
    sys.exit(0)
except OSError as exc:
    sys.exit({_ERRNO_EXIT_OFFSET} + (exc.errno or 0))
"""
"""Mirrors `test_tiocsti_battery.py`'s own probe: reports 0 if the injection
succeeded, or `_ERRNO_EXIT_OFFSET` plus the ioctl's own errno if it was denied --
never a bare 1, so a denial can never collide with bwrap's own setup-failure exit
code or the probe-crashed sentinel.
"""


def _drain_until_closed(fd: int) -> None:
    """Discard everything `fd` carries until it closes -- see
    `test_tiocsti_battery.py`'s own `_drain_until_closed` for why a pty's master end
    needs a reader at all.
    """
    while True:
        try:
            if not os.read(fd, 4096):
                return
        except OSError:
            return


def _run_in_pty(child: Callable[[], int]) -> int:
    """Fork a process owning a freshly made pty as its own controlling terminal, run
    `child` inside it, and return its exit code. See
    `test_tiocsti_battery.py`'s own `_run_in_pty_session` for the full reasoning;
    this is the same shape, condensed for this file's two callers below.
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


def _unconfined_tiocsti_probe() -> int:
    """Run inside `_run_in_pty`: attempt TIOCSTI injection while still owning the
    pty as this process's own controlling terminal -- the positive control. Reports
    through the same errno-offset protocol as `_TIOCSTI_PROBE`, so a denied control
    is as legible as a denied violation.
    """
    try:
        fcntl.ioctl(0, termios.TIOCSTI, b"x")
        return 0
    except OSError as exc:
        return _ERRNO_EXIT_OFFSET + (exc.errno or 0)


def _jailed_tiocsti_probe() -> int:
    """Run inside `_run_in_pty`: the same probe, as a real bwrap jail's one process,
    through the public API -- the claim itself.
    """
    jail = create_bwrap_jail((sys.executable, "-c", _TIOCSTI_PROBE))
    exit_code = run_jail(jail)
    destroy_jail(jail)
    return exit_code


def _evidence_from_measured_exit_codes(control_exit: int, violation_exit: int) -> Evidence:
    """Pure classifier: turn the two exit codes `_measure_tiocsti_closure` measures
    into honest `Evidence`, never treating "not a denial" as "blocked".

    `control_exit` not `0` means the positive control never fired -- nothing here
    proved the probe could see a violation get through, so there is no evidence at
    all, regardless of what `violation_exit` says.

    Given an observed control, `violation_exit` has three distinct meanings, not
    two:
    - `0`: the injection succeeded -- the jail did not hold. A real, measured
      breach, graded `VIOLATED` by `grade()`, never collapsed into "no evidence".
    - `_ERRNO_EXIT_OFFSET + _DENIED_ERRNO`: the injection was denied for the
      specific errno a closed TIOCSTI reports. Graded `ENFORCED`.
    - anything else -- bwrap's own setup failure (exit 1, user namespaces
      disabled), `_PROBE_CRASHED_EXIT_CODE`, or any other errno (`EIO` from a
      kernel with TIOCSTI compiled out) -- means the probe never produced a result
      that says which of the two above happened. That is no evidence, not a
      fabricated `ENFORCED`: the exact bug this function exists to rule out, where
      `violation_exit != 0` alone treated every one of these as "blocked".
    """
    if control_exit != 0:
        return Evidence(control_observed=False, violation_blocked=False)
    if violation_exit == 0:
        return Evidence(control_observed=True, violation_blocked=False)
    if violation_exit == _ERRNO_EXIT_OFFSET + _DENIED_ERRNO:
        return Evidence(control_observed=True, violation_blocked=True)
    return Evidence(control_observed=False, violation_blocked=False)


def _measure_tiocsti_closure() -> Evidence | None:
    """Measure `TIOCSTI_CLOSURE_CLAIM` against a real bwrap jail, or report no
    evidence at all where there is nothing real to measure against: `bwrap` not
    installed on this host (macOS). Where bwrap is installed,
    `_evidence_from_measured_exit_codes` turns the two measured exit codes into
    `Evidence`, honestly distinguishing a denied injection from a successful one
    from a probe that never produced either result (this kernel's TIOCSTI compiled
    out, bwrap's own setup failing, the probe crashing) -- see that function's own
    docstring for why a bare `!= 0` cannot stand in for that distinction.
    """
    if shutil.which("bwrap") is None:
        return None
    control_exit = _run_in_pty(_unconfined_tiocsti_probe)
    if control_exit != 0:
        return _evidence_from_measured_exit_codes(control_exit, violation_exit=0)
    violation_exit = _run_in_pty(_jailed_tiocsti_probe)
    return _evidence_from_measured_exit_codes(control_exit, violation_exit)


def test_fd_inheritance_claim_grades_enforced_from_real_evidence() -> None:
    """The fd-inheritance claim, measured for real through the gateway `spawn` --
    needs no bwrap, so this is a real `ENFORCED`, not a hoped-for one, on every host
    this suite runs on.
    """
    evidence = {FD_INHERITANCE_CLAIM: _measure_fd_inheritance()}

    report = grade((FD_INHERITANCE_CLAIM,), evidence)

    assert report == {FD_INHERITANCE_CLAIM: Grade.ENFORCED}


def test_tiocsti_closure_claim_grades_from_whatever_this_host_can_measure() -> None:
    """The TIOCSTI-closure claim, measured against a real bwrap jail where one is
    available (Linux, in CI) and left with no evidence -- grading `UNENFORCED`,
    never a fabricated `ENFORCED` -- where it is not (macOS, locally; see this
    file's own module docstring for why skipping cannot stand in for that here).
    """
    measured = _measure_tiocsti_closure()
    evidence = {} if measured is None else {TIOCSTI_CLOSURE_CLAIM: measured}

    report = grade((TIOCSTI_CLOSURE_CLAIM,), evidence)

    # Four honest outcomes: no bwrap to measure against at all (measured is None);
    # bwrap present but this kernel never let the positive control through
    # (measured.control_observed is False); bwrap present, control observed, and the
    # injection actually got through -- a real measured breach, VIOLATED, never
    # softened into UNENFORCED; and bwrap present, control observed, injection
    # denied -- the one case that must grade ENFORCED.
    if measured is None or not measured.control_observed:
        assert report == {TIOCSTI_CLOSURE_CLAIM: Grade.UNENFORCED}
    elif measured.violation_blocked:
        assert report == {TIOCSTI_CLOSURE_CLAIM: Grade.ENFORCED}
    else:
        assert report == {TIOCSTI_CLOSURE_CLAIM: Grade.VIOLATED}


def test_tiocsti_evidence_classifier_only_grades_blocked_from_the_exact_denial_code() -> None:
    """Covers `_evidence_from_measured_exit_codes`'s branches directly, with plain
    integers standing in for the exit codes `_measure_tiocsti_closure` would
    otherwise only produce on a real bwrap jail -- unavailable on this host (macOS),
    so this is the one place the bug this function fixes (treating any non-zero
    exit as "blocked") gets exercised on every host, not only in CI on Linux.
    """
    denied = _ERRNO_EXIT_OFFSET + _DENIED_ERRNO

    # No positive control observed: no evidence at all, whatever the violation
    # probe reported (it should not even be trusted).
    assert _evidence_from_measured_exit_codes(control_exit=1, violation_exit=denied) == Evidence(
        control_observed=False, violation_blocked=False
    )

    # Control observed, injection denied for the exact expected errno: ENFORCED.
    assert _evidence_from_measured_exit_codes(control_exit=0, violation_exit=denied) == Evidence(
        control_observed=True, violation_blocked=True
    )

    # Control observed, injection succeeded: a real breach, VIOLATED -- not no
    # evidence, and not ENFORCED.
    assert _evidence_from_measured_exit_codes(control_exit=0, violation_exit=0) == Evidence(
        control_observed=True, violation_blocked=False
    )

    # Control observed, but the violation probe never reached either outcome:
    # bwrap's own setup failure (exit 1), a crashed probe, and an unrelated errno
    # (EIO, a kernel with TIOCSTI compiled out) must all read as no evidence, never
    # a fabricated ENFORCED -- this is the exact bug `violation_exit != 0` had.
    for ambiguous_exit in (1, _PROBE_CRASHED_EXIT_CODE, _ERRNO_EXIT_OFFSET + errno.EIO):
        assert _evidence_from_measured_exit_codes(
            control_exit=0, violation_exit=ambiguous_exit
        ) == Evidence(control_observed=False, violation_blocked=False)
