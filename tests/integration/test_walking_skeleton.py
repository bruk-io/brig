"""Integration test for the walking skeleton: create a bwrap jail, run `true` in it, destroy
it, through brig's public API with `FakeProcesses` and `FakeSupervisors` at infra's edge.
"""

from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import create_bwrap_jail, destroy_jail, run_jail


def test_bwrap_walking_skeleton_runs_true_and_tears_down_clean() -> None:
    """Create, run and destroy a bwrap jail for `true`, crossing every layer. The jail's one
    process is its supervisor (decision-0002); `alive` stays `False`, so teardown's first
    `Verify` finds the group gone and nothing is signalled."""
    processes = FakeProcesses()
    supervisors = FakeSupervisors()

    jail = create_bwrap_jail(("true",), processes=processes, supervisors=supervisors)
    exit_code = run_jail(jail, processes=processes, supervisors=supervisors)
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert exit_code == 0
    # The supervisor runs the command as `compile_run` left it, with no environment.
    assert supervisors.started == [(("true",), frozendict())]
    assert [pid for pid, _ in supervisors.awaited] == [jail.process.pid]
    assert supervisors.closed == [jail.process.pid]
    # The one Verify peeks the supervisor, holds nothing (it has not exited) and finds the
    # group gone.
    assert processes.peek_attempts == [jail.process.pid]
    assert processes.checked == [jail.process.pgid]
    assert processes.checked_held == [frozenset()]
    assert processes.signalled == []
    # The ladder's last step releases the supervisor's pid once, even on this path.
    assert processes.released == [jail.process.pid]
