"""Integration test for `run_jail` telling an unobtainable exit code apart from a
timeout (review finding 3 on TASK-0001.06).

Runs the create-then-wait part of the journey through brig's public API, with
`FakeProcesses` arranged so its `reap_deadline` reports the process is no longer this
program's child to wait for at all (`process_unknown=True`) -- the shape an embedder
that auto-reaps its own children gives `run_jail`, and which `reap_deadline` used to
conflate with an ordinary deadline expiry (both reported as `None`). `run_jail` must
raise `JailExitUnknown`, not `JailWaitTimedOut`: unlike a deadline that merely passed,
no later wait could ever recover this process's exit code. Nothing inside brig's own
code is faked or patched (rule 5); only the world at the edge is.
"""

import pytest
from tests.integration.fakes import FakeProcesses

from brig import JailExitUnknown, JailWaitTimedOut, create_bwrap_jail, run_jail


def test_run_jail_raises_jail_exit_unknown_not_timed_out_when_reaped_elsewhere() -> None:
    """`run_jail` raises `JailExitUnknown` when the process is no longer this
    program's child to wait for at all, never the `JailWaitTimedOut` a genuine
    deadline expiry raises.
    """
    processes = FakeProcesses(process_unknown=True)
    jail = create_bwrap_jail(("true",), processes=processes)

    with pytest.raises(JailExitUnknown) as excinfo:
        run_jail(jail, timeout_s=5.0, processes=processes)

    assert excinfo.value.process == jail.process
    assert not isinstance(excinfo.value, JailWaitTimedOut)
    assert [pid for pid, _ in processes.reaped_deadline] == [jail.process.pid]
