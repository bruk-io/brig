"""Integration test for the walking skeleton (TASK-0001.03).

Runs the whole journey -- create a bwrap jail, run `true` in it, destroy it --
through brig's public API, with `FakeProcesses` wired in at infra's edge instead of
`brig.infra.processes`. Nothing inside brig's own code is faked or patched (rule 5);
only the world at the edge is, and the test asserts on its recorded state plus the
journey's reported outcome.
"""

from tests.integration.fakes import FakeProcesses

from brig import create_bwrap_jail, destroy_jail, run_jail


def test_bwrap_walking_skeleton_runs_true_and_tears_down_clean() -> None:
    """Create, run and destroy a bwrap jail for `true`, crossing every layer.

    `true` exits 0 on its own and leaves nothing behind, so the fake's `alive`
    stays at its default `False`: teardown's first `Verify` finds the group
    already gone and the kill ladder never signals it at all. `run_jail` always
    waits with a deadline (TASK-0001.06), so the exit is collected through
    `reap_deadline`, never the undeadlined `reap`.
    """
    processes = FakeProcesses()

    jail = create_bwrap_jail(("true",), processes=processes)
    exit_code = run_jail(jail, processes=processes)
    destroy_jail(jail, processes=processes)

    assert exit_code == 0
    assert processes.spawned == [
        (
            "bwrap",
            "--ro-bind",
            "/",
            "/",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--",
            "true",
        )
    ]
    # TASK-0001.05 AC#1: bwrap's own allow-list (just its standard streams) reaches
    # the edge on the same Spawn call as the argv -- never silently dropped en route.
    assert processes.spawned_inheritable_fds == [(0, 1, 2)]
    assert processes.reaped == []
    assert [pid for pid, _ in processes.reaped_deadline] == [jail.process.pid]
    assert processes.checked == [jail.process.pgid]
    assert processes.signalled == []
