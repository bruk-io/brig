"""Integration test for the walking skeleton (TASK-0001.03; re-pointed at the
supervised path by TASK-0001.15 step 4).

Runs the whole journey -- create a bwrap jail, run `true` in it, destroy it --
through brig's public API, with `FakeProcesses` and `FakeSupervisors` wired in at
infra's edge instead of `brig.infra.processes`/`brig.infra.supervisor.link`.
Nothing inside brig's own code is faked or patched (rule 5); only the world at the
edge is, and the test asserts on its recorded state plus the journey's reported
outcome.
"""

from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import create_bwrap_jail, destroy_jail, run_jail


def test_bwrap_walking_skeleton_runs_true_and_tears_down_clean() -> None:
    """Create, run and destroy a bwrap jail for `true`, crossing every layer.

    The jail's one process is now its supervisor (decision-0002): `create_bwrap_jail`
    starts it through `FakeSupervisors`, never `FakeProcesses.spawn` -- that fake's
    own `alive` stays at its default `False`, so teardown's first `Verify` finds the
    supervisor's group already gone and the kill ladder never signals it at all.
    `run_jail` always waits with a deadline (TASK-0001.06), so the exit is collected
    through `FakeSupervisors.await_done`, never a direct `reap`.
    """
    processes = FakeProcesses()
    supervisors = FakeSupervisors()

    jail = create_bwrap_jail(("true",), processes=processes, supervisors=supervisors)
    exit_code = run_jail(jail, processes=processes, supervisors=supervisors)
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert exit_code == 0
    # decision-0002: the supervisor runs the real command, named exactly as
    # `compile_run` left it -- bwrap's own flags no longer wrap it directly.
    assert supervisors.started == [(("true",), ())]
    assert [pid for pid, _ in supervisors.awaited] == [jail.process.pid]
    assert supervisors.closed == [jail.process.pid]
    # Nothing is spawned directly any more: the jail's one process is the
    # supervisor FakeSupervisors started, never a Spawn through FakeProcesses.
    assert processes.spawned == []
    assert processes.reaped == []
    assert processes.reaped_deadline == []
    # Teardown's own ladder is unchanged: it still verifies and (if needed) signals
    # the jail's one process -- the supervisor's pid/pgid now, not the real
    # command's. `FakeProcesses.leader_exited` defaults to `False` here (nothing
    # arranges the supervisor as a peeked, held zombie), so the one Verify's own
    # peek excludes nothing (`held == frozenset()`) and its answer comes straight
    # from `alive` -- still `False` by default, so the group reads gone at once.
    assert processes.peek_attempts == [jail.process.pid]
    assert processes.checked == [jail.process.pgid]
    assert processes.checked_held == [frozenset()]
    assert processes.signalled == []
    # decision-0003/TASK-0013: the ladder's terminal step releases the supervisor's
    # pid exactly once, even on this already-gone, never-signalled path.
    assert processes.released == [jail.process.pid]
