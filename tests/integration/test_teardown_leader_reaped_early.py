"""Integration test for teardown tolerating a leader reaped before its group (review
findings 1 and 2 on TASK-0001.06).

Runs `destroy_jail` through brig's public API, with `FakeProcesses` arranged so the
group answers alive for the ladder's first two `Verify` calls (the leader has exited
and been collected by an earlier `Verify`'s own non-blocking `reap_nowait`, but a
grandchild of it keeps the rest of the group alive) before finally reporting gone,
and so the post-KILL `Reap` finds the leader already reaped (`ProcessUnknown`) rather
than collecting an exit code of its own. Before this fix, that `Reap` leaked a raw
`ChildProcessError` out of `destroy_jail` -- a non-brig exception crossing the public
API (decision-0001 rule 13) on exactly the kind of multi-process group a real bwrap
jail is. Nothing inside brig's own code is faked or patched (rule 5); only the world
at the edge is.

This proves the crash is gone and the ladder's shape is unchanged, against a fake
that always answers instantly -- it cannot exercise real `SIGKILL` timing, so it
cannot show whether the final `Verify` here would, against a real multi-process
group, ever still see the group alive for a few more moments while the kernel
finishes what `KILL` started. That is a real, separately confirmed race (see
`teardown.py`'s own docstring and TASK-0001.07) this test does not speak to.
"""

import signal

from tests.integration.fakes import FakeProcesses

from brig import create_bwrap_jail, destroy_jail


def test_destroy_jail_tolerates_leader_reaped_before_the_rest_of_its_group() -> None:
    """`destroy_jail` completes, verified, even though the leader was already gone by
    the time the kill ladder's last `Reap` goes looking for it.
    """
    processes = FakeProcesses(alive_checks=2, process_unknown=True)
    jail = create_bwrap_jail(("sleep", "9999"), processes=processes)

    destroy_jail(jail, processes=processes)

    assert processes.signalled == [
        (jail.process.pgid, signal.SIGTERM),
        (jail.process.pgid, signal.SIGKILL),
    ]
    assert processes.reaped == [jail.process.pid]
    assert processes.checked == [jail.process.pgid] * 3
