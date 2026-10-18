"""Integration test for a deadline-bound wait that expires (TASK-0001.06;
re-pointed at the supervised path by TASK-0001.15 step 4).

Runs the create-then-wait part of the journey through brig's public API, with
`FakeSupervisors` arranged so its `await_done` reports its deadline passed
(`expires`) instead of an exit code -- the shape a jailed process that never exits
on its own gives `run_jail`. Nothing inside brig's own code is faked or patched
(rule 5); only the world at the edge is.
"""

import pytest
from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import JailWaitTimedOut, create_bwrap_jail, run_jail


def test_run_jail_raises_when_the_wait_passes_its_deadline() -> None:
    """`run_jail` raises `JailWaitTimedOut` instead of blocking when the deadline passes.

    `expires=True` has the fake's `await_done` report `None` -- a wait that gave up
    at its deadline with the process still unreaped -- so `run_jail` must turn that
    into `JailWaitTimedOut` rather than returning or hanging.
    """
    processes = FakeProcesses()
    supervisors = FakeSupervisors(expires=True)
    jail = create_bwrap_jail(("true",), processes=processes, supervisors=supervisors)

    with pytest.raises(JailWaitTimedOut) as excinfo:
        run_jail(jail, timeout_s=0.01, processes=processes, supervisors=supervisors)

    assert excinfo.value.process == jail.process
    assert [pid for pid, _ in supervisors.awaited] == [jail.process.pid]
