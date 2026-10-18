"""Integration test for `run_jail` telling an unobtainable exit code apart from a
timeout (review finding 3 on TASK-0001.06; re-pointed at the supervised path by
TASK-0001.15 step 4).

Runs the create-then-wait part of the journey through brig's public API, with
`FakeSupervisors` arranged so its `await_done` reports the supervisor's report for
this process as gone for good (`done_unknown=True`) -- the shape a supervisor that
can never answer again gives `run_jail`, and which `await_done` must never conflate
with an ordinary deadline expiry (both of which `Reap`'s own earlier review found
reported as `None`). `run_jail` must raise `JailExitUnknown`, not `JailWaitTimedOut`:
unlike a deadline that merely passed, no later wait could ever recover this
process's exit code. Nothing inside brig's own code is faked or patched (rule 5);
only the world at the edge is.
"""

import pytest
from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import JailExitUnknown, JailWaitTimedOut, create_bwrap_jail, run_jail


def test_run_jail_raises_jail_exit_unknown_not_timed_out_when_reaped_elsewhere() -> None:
    """`run_jail` raises `JailExitUnknown` when the supervisor's report for this
    process can never be recovered, never the `JailWaitTimedOut` a genuine deadline
    expiry raises.
    """
    processes = FakeProcesses()
    supervisors = FakeSupervisors(done_unknown=True)
    jail = create_bwrap_jail(("true",), processes=processes, supervisors=supervisors)

    with pytest.raises(JailExitUnknown) as excinfo:
        run_jail(jail, timeout_s=5.0, processes=processes, supervisors=supervisors)

    assert excinfo.value.process == jail.process
    assert not isinstance(excinfo.value, JailWaitTimedOut)
    assert [pid for pid, _ in supervisors.awaited] == [jail.process.pid]
