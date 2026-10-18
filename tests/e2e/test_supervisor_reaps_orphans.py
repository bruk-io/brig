"""E2E test for the supervisor's own PID-1 claim, against a real bwrap jail
(TASK-0001.15 step 5): decision-0002's premise that a jail's supervisor reaps not
only the command it starts directly, but every orphan reparented to it afterward --
because it genuinely is PID 1 inside the jail's own namespace, not merely something
the host happens to track.

`tests/e2e/test_supervisor_program_gateway.py`'s own gateway test cannot show this
half: outside a real PID namespace, a process that test spawns directly is not a
subreaper, so a grandchild its own child leaves behind reparents to the host's real
init, never to that test -- the orphan-reaping claim is only observable with a real
PID namespace, `--as-pid-1` included (`domain/jail_types/bwrap.py`'s own docstring
measures exactly this: without that flag, bwrap's own reaper takes the role
instead, not the supervisor). This test provides that real namespace, through the
public API, and so is this task's own positive evidence for the half the gateway
test could not reach.

Guarded to skip cleanly on hosts without bwrap (macOS); runs for real in CI on
Linux.
"""

import shutil
import sys
import time

import pytest

from brig import create_bwrap_jail, destroy_jail, run_jail

_ORPHAN_SLEEP_S = 2.0
"""How long the orphan outlives its own parent: long enough that "done arrived
almost instantly" and "done arrived only once the orphan was also reaped" are never
ambiguous on any host this runs on, short enough not to make this test slow.
"""

_LEADER_EXIT_CODE = 5
"""The directly-started command's own exit code -- distinct from 0 (an ordinary
clean exit) and from any shell or interpreter failure, so a wrong value could not
be mistaken for one of those instead of a real assertion failure.
"""

_ORPHAN_LEAVING_COMMAND = (
    sys.executable,
    "-c",
    (
        "import os, sys, time\n"
        "if os.fork() == 0:\n"
        f"    time.sleep({_ORPHAN_SLEEP_S!r})\n"
        "    sys.exit(0)\n"
        f"sys.exit({_LEADER_EXIT_CODE})\n"
    ),
)
"""Forks once, then the parent (this jail's own directly-started command) exits
immediately with `_LEADER_EXIT_CODE`, leaving its own child behind -- an orphan,
reparented inside the jail's namespace to whatever is PID 1 there. Absolute paths
only (`sys.executable`, no shell): the supervised command runs with no environment
at all today (`domain/plan.py`'s own "known gap"), so nothing here depends on
`PATH` existing to resolve a bare name.
"""


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_supervisor_waits_for_an_orphan_reparented_to_it_before_reporting_done() -> None:
    """`run_jail` must not return once the directly-started command exits -- it
    must wait for the orphan it left behind too, since nothing else inside the
    jail's namespace will ever reap it otherwise (`program.py`'s own module
    docstring). The wait's own wall-clock time is the evidence: no event on the
    wire ever names the orphan at all (`wire.py`'s `_DoneEvent` docstring: an
    orphan is "an orphan this process owes no event to"), so "waited long enough
    for the orphan to finish" is the only way to observe this from outside. The
    directly-started command's own exit code must still come through unchanged,
    proving the orphan's own reaping never overwrites it.
    """
    jail = create_bwrap_jail(_ORPHAN_LEAVING_COMMAND)

    started_at = time.monotonic()
    exit_code = run_jail(jail)
    elapsed_s = time.monotonic() - started_at

    destroy_jail(jail)

    assert exit_code == _LEADER_EXIT_CODE
    assert elapsed_s >= _ORPHAN_SLEEP_S - 0.5, (
        f"run_jail returned after only {elapsed_s:.2f}s, well under the orphan's own "
        f"{_ORPHAN_SLEEP_S}s sleep -- it reported done without waiting for the orphan"
    )
