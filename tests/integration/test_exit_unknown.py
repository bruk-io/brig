"""Integration test: `run_jail` raises `JailExitUnknown`, not `JailWaitTimedOut`, when the
supervisor's report is gone for good (`FakeSupervisors(done_unknown=True)`); no later wait could
recover it."""

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
