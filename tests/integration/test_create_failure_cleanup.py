"""TASK-0044 beyond its repro: every step of `create_bwrap_jail` after the supervisor's start
(the placeholder attach, the namespace scan) cleans up through the cleanup `destroy_jail` runs,
so a jail that could not be created is torn down, verified, and its placeholders are released
only once the teardown reads its group gone. A failure before the start has no process to tear
down and releases at once; `destroy_jail` gates the release the same way.

The world is faked at infra's edge (decision-0001 rule 5): `FakeProcesses` says whether the
group dies (`alive_checks=1`: gone after TERM) or never does (`alive=True`), and
`FakePlaceholders` records what was held, attached and released. The scan fails at once on a
`proc_root` that does not exist, so no test here waits out `JAIL_PID1_TIMEOUT_S`.
"""

import signal
from pathlib import Path

import pytest
from tests.integration.fakes import (
    FakeChannelDirectories,
    FakePlaceholders,
    FakeProcesses,
    FakeSupervisors,
    plant_fake_proc,
)

from brig import (
    Channel,
    ChannelDirectoryCreateFailed,
    ChannelNamespaceNotFound,
    JailTeardownFailed,
    PlaceholdersFailed,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
)

_SUPERVISOR_PID = 2000
"""`FakeSupervisors`'s first fabricated pid, and its pgid."""


def _create(
    tmp_path: Path,
    step: str,
    processes: FakeProcesses,
    supervisors: FakeSupervisors,
    placeholders: FakePlaceholders,
    directories: FakeChannelDirectories,
) -> None:
    """A channel-declaring create whose `step` fails: `attach` through the placeholder port
    (the scan's `/proc` then holds a PID 1, so only the attach fails), `scan` through a
    `proc_root` that cannot be listed."""
    proc_root = str(tmp_path / "proc")
    if step == "attach":
        placeholders.fail_attach = True
        plant_fake_proc(
            proc_root,
            {_SUPERVISOR_PID: (1, str(_SUPERVISOR_PID)), 2001: (_SUPERVISOR_PID, "2001\t1")},
        )
    create_bwrap_jail(
        ("server",),
        channels=reserve_channels((Channel("ctl"),), directories=directories),
        processes=processes,
        supervisors=supervisors,
        directories=directories,
        placeholders=placeholders,
        proc_root=proc_root,
    )


_STEPS = [("attach", PlaceholdersFailed), ("scan", ChannelNamespaceNotFound)]


@pytest.mark.parametrize(("step", "raised"), _STEPS, ids=["attach", "scan"])
def test_a_step_after_the_start_tears_down_then_releases(
    tmp_path: Path, step: str, raised: type[Exception]
) -> None:
    """The group dies after TERM: the step's own error propagates, the supervisor was torn
    down and closed, and only then were the placeholders released."""
    processes = FakeProcesses(alive_checks=1)
    supervisors = FakeSupervisors()
    placeholders = FakePlaceholders()
    directories = FakeChannelDirectories()

    with pytest.raises(raised):
        _create(tmp_path, step, processes, supervisors, placeholders, directories)

    assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
    assert processes.released == [_SUPERVISOR_PID]
    assert supervisors.closed == [_SUPERVISOR_PID]
    assert placeholders.released == [placeholders.record]
    assert directories.removed == [directories.path]


@pytest.mark.parametrize(("step", "raised"), _STEPS, ids=["attach", "scan"])
def test_a_step_after_the_start_whose_teardown_fails_releases_nothing(
    tmp_path: Path, step: str, raised: type[Exception]
) -> None:
    """The group survives TERM and KILL: `JailTeardownFailed` names the supervisor, the
    step's own error is its cause, and the placeholders the live jail mounts over are kept."""
    processes = FakeProcesses(alive=True)
    supervisors = FakeSupervisors()
    placeholders = FakePlaceholders()
    directories = FakeChannelDirectories()

    with pytest.raises(JailTeardownFailed) as failed:
        _create(tmp_path, step, processes, supervisors, placeholders, directories)

    assert failed.value.process.pid == _SUPERVISOR_PID
    assert isinstance(failed.value.__cause__, raised)
    assert processes.signalled == [
        (_SUPERVISOR_PID, signal.SIGTERM),
        (_SUPERVISOR_PID, signal.SIGKILL),
    ]
    assert supervisors.closed == [_SUPERVISOR_PID]
    assert placeholders.released == []
    assert directories.removed == [directories.path]


def test_a_failure_before_the_start_releases_at_once_and_signals_nothing() -> None:
    """The channel directory cannot be made, so nothing started: no verify, no signal, and the
    placeholders held before it are released."""
    processes = FakeProcesses(alive=True)
    supervisors = FakeSupervisors()
    placeholders = FakePlaceholders()
    directories = FakeChannelDirectories(fail_create=True)

    with pytest.raises(ChannelDirectoryCreateFailed):
        create_bwrap_jail(
            ("server",),
            channels=reserve_channels((Channel("ctl"),), directories=directories),
            processes=processes,
            supervisors=supervisors,
            directories=directories,
            placeholders=placeholders,
        )

    assert supervisors.started == []
    assert processes.checked == []
    assert processes.signalled == []
    assert placeholders.released == [placeholders.record]


@pytest.mark.parametrize("alive", [False, True], ids=["gone", "alive"])
def test_destroy_jail_releases_only_once_the_group_is_gone(alive: bool) -> None:
    """The same gate on the other path: `destroy_jail` releases the jail's placeholders when
    its teardown reads the group gone, and keeps them when it raises `JailTeardownFailed`."""
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    placeholders = FakePlaceholders()
    jail = create_bwrap_jail(
        ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
    )
    assert placeholders.attached == [(placeholders.record, _SUPERVISOR_PID)]
    assert jail.placeholders == placeholders.record
    processes.alive = alive

    if alive:
        with pytest.raises(JailTeardownFailed):
            destroy_jail(jail, processes=processes, placeholders=placeholders)
        assert placeholders.released == []
    else:
        destroy_jail(jail, processes=processes, placeholders=placeholders)
        assert placeholders.released == [placeholders.record]
