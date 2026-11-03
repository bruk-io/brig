"""TASK-0044's repro: a `create_bwrap_jail` that fails once its supervisor has started leaves
that supervisor running, with no `Jail` for the embedder to hand `destroy_jail`.

The step that fails here is the namespace scan: a channel-declaring create looks for the jail's
PID 1 under the supervisor it started, and the planted `/proc` has the supervisor alive with no
PID 1 under it, so the scan raises `ChannelNamespaceNotFound` (documented "with process still
running") once `JAIL_PID1_TIMEOUT_S` passes. By then a process exists, so the failure must tear it
down through the verified kill ladder, the way `destroy_jail` does: `FakeProcesses` reads the
group alive at the first verify and gone after TERM, so the ladder sends TERM and releases the
supervisor's pid. The world is faked at infra's edge only (decision-0001 rule 5).
"""

import signal
from pathlib import Path

import pytest
from tests.integration.fakes import (
    FakeChannelDirectories,
    FakeProcesses,
    FakeSupervisors,
    plant_fake_proc,
)

from brig import Channel, ChannelNamespaceNotFound, create_bwrap_jail, reserve_channels

_SUPERVISOR_PID = 2000
"""`FakeSupervisors`'s first fabricated pid, and its pgid: the process the scan is rooted at."""


def test_a_failed_namespace_scan_tears_the_started_supervisor_down(tmp_path: Path) -> None:
    """The scan finds no PID 1 under a running supervisor: `ChannelNamespaceNotFound` still
    propagates, and before it does the supervisor's group was verified, sent TERM, verified
    gone and its pid released, and its events pipe closed."""
    proc_root = str(tmp_path / "proc")
    plant_fake_proc(proc_root, {_SUPERVISOR_PID: (1, str(_SUPERVISOR_PID))})
    directories = FakeChannelDirectories()
    processes = FakeProcesses(alive_checks=1)
    supervisors = FakeSupervisors()
    reserved = reserve_channels((Channel("ctl"),), directories=directories)

    with pytest.raises(ChannelNamespaceNotFound):
        create_bwrap_jail(
            ("server",),
            channels=reserved,
            processes=processes,
            supervisors=supervisors,
            directories=directories,
            proc_root=proc_root,
        )

    assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
    assert processes.released == [_SUPERVISOR_PID]
    assert supervisors.closed == [_SUPERVISOR_PID]
    assert directories.removed == [directories.path]
