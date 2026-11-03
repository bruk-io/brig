"""Integration test for teardown with a leader that exits before the rest of its group
(decision-0003): `FakeProcesses(leader_exited=True, alive_checks=2)` keeps the group alive
through two `Verify` calls before the post-KILL poll finds it gone. A held leader is never read
as the group being alive, and its pid is released once. The real `SIGKILL` timing is proven
against bwrap (TASK-0001.07)."""

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
