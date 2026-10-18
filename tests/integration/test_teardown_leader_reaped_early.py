"""Integration test for teardown tolerating a leader that exits before the rest of
its group (review findings 1 and 2 on TASK-0001.06; redesigned by decision-0003/
TASK-0013's peek-before-release split).

Runs `destroy_jail` through brig's public API, with `FakeProcesses` arranged so the
leader has already exited (`leader_exited=True`) while a grandchild of it keeps the
rest of the group alive for the ladder's first two `Verify` calls (`alive_checks=2`)
before the post-KILL rung's grace-window poll finally finds the group gone. Nothing
inside brig's own code is faked or patched (rule 5); only the world at the edge is.

Before TASK-0001.06's own fix, a leader reaped early leaked a raw `ChildProcessError`
out of `destroy_jail` through the post-KILL `Reap` that no longer exists -- the
`Reap`-as-synchronization-barrier redesign decision-0003 made means that scenario has
nothing left to pin here (`tests/unit/test_teardown.py`'s own module docstring has
the full reasoning). What this test now proves instead: a leader excluded as a
deliberately held pid is never read as "this group is still alive" on its own, and
teardown still releases that pid exactly once before `destroy_jail` returns.

This proves the ladder's shape against a fake that always answers instantly -- it
cannot exercise real `SIGKILL` timing, so it cannot show whether the post-KILL rung's
grace window actually closes the real race against a genuine multi-process group.
That is proven separately, for real, against bwrap (TASK-0001.07).
"""

import signal

from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import create_bwrap_jail, destroy_jail


def test_destroy_jail_tolerates_leader_exiting_before_the_rest_of_its_group() -> None:
    """`destroy_jail` completes, verified, even though the leader exited well before
    the rest of its group did -- excluded from every `group_alive` check as a
    deliberately held pid, and released exactly once at the very end.
    """
    processes = FakeProcesses(alive_checks=2, leader_exited=True)
    supervisors = FakeSupervisors()
    jail = create_bwrap_jail(("sleep", "9999"), processes=processes, supervisors=supervisors)

    destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert processes.signalled == [
        (jail.process.pgid, signal.SIGTERM),
        (jail.process.pgid, signal.SIGKILL),
    ]
    assert processes.released == [jail.process.pid]
    held = frozenset({jail.process.pid})
    # Two immediate Verify calls (before and after TERM), then the post-KILL rung's
    # grace-window poll -- which, in the fake, resolves after exactly one more
    # group_alive check of its own (`FakeProcesses.group_alive_deadline`'s own
    # docstring: it never actually polls or sleeps).
    assert processes.checked == [jail.process.pgid] * 3
    assert processes.checked_held == [held] * 3
    assert processes.checked_deadline == [
        (jail.process.pid, jail.process.pgid, processes.checked_deadline[0][2])
    ]
