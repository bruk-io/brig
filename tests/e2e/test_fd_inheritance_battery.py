"""E2E battery for the fd-inheritance hole (TASK-0001.05 AC#1, AC#3).

The realistic hazard decision-0001 names is not "a fd leaks by default" -- CPython
has marked nearly every fd it creates non-inheritable since PEP 446 -- but an fd an
embedder explicitly marked inheritable itself, for its own purposes (IPC, say),
surviving the spawn and reaching the jailed process regardless of the filesystem
policy or namespaces around it, since a fd bypasses both entirely.

This file has two batteries, each with its own positive control (rule 11: evidence,
not a happy path alone):

- A gateway battery against `brig.infra.processes.spawn` directly (decision-0001 rule
  4 lets an e2e test import one `brig.infra` module for exactly this): a pipe fd this
  test marks inheritable by hand, carrying a known payload, read back by a probe
  command through a second, dedicated fd. Grades the close path's own mechanics, with
  an allow-list this test supplies itself; runs everywhere, no bwrap needed.
- A real-jail battery against the same hole through `create_bwrap_jail`/`run_jail` --
  the public API, with no allow-list this test supplies -- so what is graded is the
  actual claim: that the bwrap jail type's own stated allow-list
  (`domain/jail_types/bwrap.py`'s `_INHERITABLE_FDS`) reaches a real jail. Guarded to
  skip cleanly where bwrap is not installed (macOS); runs for real in CI on Linux.

Rule 5 forbids `unittest.mock`/`monkeypatch` anywhere in this suite, so every positive
control below is a second real run -- the one fact under test changed, nothing
patched -- never a patched one.
"""

import os
import shutil
import sys

import pytest

from brig import create_bwrap_jail, destroy_jail, run_jail
from brig.infra.processes import reap, spawn

_STDIO_FDS = (0, 1, 2)
"""The allow-list every probe spawn below grants beyond the fds under test: standard
streams only, so the probe process can be started and reaped normally.
"""

_PLANTED_PAYLOAD = b"leaked-secret"
"""Known bytes written into the planted pipe before the probe spawns, so the probe's
report can be checked against an exact value, not just "some bytes arrived".
"""

_PROBE = """
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
"""The probe command, run as `python -c <this>`: tries to read the fd named by its
first argument, and writes what it saw -- the payload if the fd was still open,
`CLOSED:<errno>` if it was not -- to the fd named by its second argument.
"""


def _run_fd_probe(*, plant_on_allow_list: bool) -> bytes:
    """Plant an inheritable pipe fd carrying `_PLANTED_PAYLOAD`, spawn the probe
    above, and return what it reported seeing.

    `plant_on_allow_list` is the one difference between the battery's main case and
    its positive control: `False` leaves the planted fd off `spawn`'s own allow-list,
    so the close path must close it before the probe runs; `True` names it, so the
    close path must leave it alone. The probe command, the payload, and every other
    fd involved are identical between the two calls -- only the allow-list changes,
    and only production code (`brig.infra.processes.spawn`) decides what happens to
    the fd either way.
    """
    planted_read_fd, planted_write_fd = os.pipe()
    report_read_fd, report_write_fd = os.pipe()
    try:
        os.write(planted_write_fd, _PLANTED_PAYLOAD)
        os.close(planted_write_fd)

        # os.pipe()'s own fds are non-inheritable by default (PEP 446); marking the
        # read end inheritable by hand is what stands in for an embedder's own IPC
        # fd -- the one case this hole is about, not an ordinary fd nobody opted in.
        os.set_inheritable(planted_read_fd, True)
        os.set_inheritable(report_write_fd, True)

        allowed = (
            (*_STDIO_FDS, report_write_fd, planted_read_fd)
            if plant_on_allow_list
            else (*_STDIO_FDS, report_write_fd)
        )
        process = spawn(
            (sys.executable, "-c", _PROBE, str(planted_read_fd), str(report_write_fd)),
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


def test_fd_marked_inheritable_is_closed_before_the_spawned_process_runs() -> None:
    """AC#1 / AC#3's planted violation, at the gateway `brig.infra.processes.spawn`
    itself: a fd this test marked inheritable, but did not name on `spawn`'s
    allow-list, is unreadable in the process `spawn` starts -- the close path closed
    it before the probe ever ran, so it cannot bypass the jail the way an unclosed
    IPC fd would.

    This grades the close path's own mechanics with a list this test supplies
    itself; `test_fd_marked_inheritable_is_closed_in_a_real_bwrap_jail` below grades
    the actual claim -- that the bwrap jail type's own stated allow-list reaches
    this same path through the public API, with nothing hand-supplied.
    """
    report = _run_fd_probe(plant_on_allow_list=False)

    # errno 9 is EBADF on every POSIX platform this runs on: a fd number simply not
    # open any more, not some other failure the probe's `except OSError` also
    # catches and that a loose `startswith(b"CLOSED:")` would let masquerade as this.
    assert report == b"CLOSED:9"


def test_positive_control_the_same_fd_leaks_through_when_it_is_on_the_allow_list() -> None:
    """Rule 11's positive control: change nothing but the allow-list, and the exact
    same planted fd reads back its exact payload -- proof the probe above can see an
    open fd and would have reported it, so the test above's "closed" result is
    evidence the close path acted on this fd, not an artifact of a probe that could
    never have detected a leak in the first place.
    """
    report = _run_fd_probe(plant_on_allow_list=True)

    assert report == b"READABLE:" + _PLANTED_PAYLOAD


_FSTAT_PROBE = """
import os, sys
target_fd = int(sys.argv[1])
try:
    os.fstat(target_fd)
    sys.exit(0)  # still open
except OSError:
    sys.exit(1)  # closed
"""
"""A second probe, for the real-bwrap battery below: `os.fstat` on the named fd
answers "is it open" with nothing but an exit code, so nothing needs reading back
out of the jail -- a report pipe would itself have to be named on bwrap's own
hardcoded allow-list (`domain/jail_types/bwrap.py`'s `_INHERITABLE_FDS`), which rule
5 forbids patching to add just for this test.
"""


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_fd_marked_inheritable_is_closed_in_a_real_bwrap_jail() -> None:
    """The claim AC#3 actually asks for, graded for real: that the bwrap jail
    type's own stated allow-list (`domain/jail_types/bwrap.py`'s `_INHERITABLE_FDS`,
    just 0/1/2) reaches a real jail through `create_bwrap_jail`/`run_jail` -- the
    public API, with no allow-list this test supplies itself the way the gateway
    battery above does.

    Plants the same kind of fd as that battery (marked inheritable by hand, not
    named on any allow-list) and runs a jail whose command probes it with
    `os.fstat` instead of reading it, so nothing has to come back out of the jail
    through a pipe bwrap's own hardcoded list does not carry.
    """
    planted_read_fd, planted_write_fd = os.pipe()
    try:
        os.close(planted_write_fd)
        os.set_inheritable(planted_read_fd, True)

        jail = create_bwrap_jail((sys.executable, "-c", _FSTAT_PROBE, str(planted_read_fd)))
        exit_code = run_jail(jail)
        destroy_jail(jail)

        assert exit_code == 1  # closed: the probe's own "still open" exit is 0
    finally:
        os.close(planted_read_fd)


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_positive_control_a_fd_on_bwraps_own_allow_list_stays_open_in_the_real_jail() -> None:
    """Rule 11's positive control for the real-jail battery above: fd 1 (stdout) is
    on bwrap's own stated allow-list and known open, so the identical probe,
    pointed at it instead of the planted fd, must report it open -- proof the probe
    can tell an open fd from a closed one inside a real bwrap jail, so the battery
    above's "closed" is evidence of this jail type's own policy, not of a probe
    that cannot detect an open fd at all.
    """
    jail = create_bwrap_jail((sys.executable, "-c", _FSTAT_PROBE, "1"))
    exit_code = run_jail(jail)
    destroy_jail(jail)

    assert exit_code == 0  # open: fd 1 is on bwrap's own allow-list
