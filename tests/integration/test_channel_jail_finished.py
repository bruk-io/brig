"""TASK-0001.30: a jail whose supervised command finishes before `create_bwrap_jail`
can find its PID namespace is not an error.

The jail's supervisor is its in-jail PID 1, and it exits right after its command
does, taking bwrap with it -- so for a command that finishes in milliseconds there is
nothing left to find. `create_bwrap_jail` then returns a `Jail` with no namespace fd,
and `await_channel_ready` answers `ChannelJailFinished` without connecting. The world
is faked at infra's edge only: a real `/proc`-shaped tree on disk (`plant_fake_proc`),
the same seam TASK-0001.27's own tests use.
"""

import time
from pathlib import Path

import pytest
from tests.integration.fakes import (
    FakeChannelDirectories,
    FakeChannelReadiness,
    FakeProcesses,
    FakeSupervisors,
    plant_fake_proc,
)

from brig import (
    Channel,
    ChannelJailFinished,
    Jail,
    Reservations,
    await_channel_ready,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
)

_SUPERVISOR_PID = 2000
"""`FakeSupervisors`'s first fabricated pid: the outer process the scan is rooted at."""


def _create(
    proc_root: str,
) -> tuple[Jail, Reservations, FakeProcesses, FakeChannelDirectories]:
    """A channel-declaring jail created against `proc_root`; returns what its tests need."""
    directories = FakeChannelDirectories()
    reserved = reserve_channels((Channel("ctl"),), directories=directories)
    processes = FakeProcesses()
    jail = create_bwrap_jail(
        ("true",),
        channels=reserved,
        processes=processes,
        supervisors=FakeSupervisors(),
        directories=directories,
        proc_root=proc_root,
    )
    return jail, reserved, processes, directories


@pytest.mark.parametrize("zombie", [False, True], ids=["entry-gone", "entry-zombie"])
def test_a_jail_whose_command_already_finished_gets_no_namespace_fd_and_no_error(
    tmp_path: Path, zombie: bool
) -> None:
    """The outer process is gone (no `/proc` entry) or a zombie nobody has reaped yet:
    `create_bwrap_jail` returns, its channel directory still recorded for teardown.
    """
    root = str(tmp_path / "proc")
    plant_fake_proc(
        root,
        {_SUPERVISOR_PID: (1, str(_SUPERVISOR_PID))} if zombie else {},
        zombies=frozenset({_SUPERVISOR_PID}),
    )

    jail, _, processes, directories = _create(root)

    assert jail.channel_namespace_fd is None
    assert jail.channel_directory == Path(directories.path)
    destroy_jail(jail, processes=processes, directories=directories)
    assert directories.removed == [directories.path]


def test_readiness_of_a_finished_jail_is_terminal_and_never_connects(tmp_path: Path) -> None:
    """`await_channel_ready` returns `ChannelJailFinished` at once, and the readiness
    port is never asked: an unverified connect there would trust whatever answered.
    """
    root = str(tmp_path / "proc")
    plant_fake_proc(root, {})
    jail, reserved, _, _ = _create(root)
    readiness = FakeChannelReadiness()

    started = time.monotonic()
    outcome = await_channel_ready(
        jail, reserved.reservations[0], timeout_s=30.0, readiness=readiness
    )

    assert outcome == ChannelJailFinished()
    assert readiness.asked == []
    assert time.monotonic() - started < 5.0


def test_a_running_jail_with_its_pid1_still_gets_its_namespace_fd(tmp_path: Path) -> None:
    """The positive control: the outer process is alive and its PID 1 child exists, so
    the scan finds it exactly as before.
    """
    root = str(tmp_path / "proc")
    plant_fake_proc(root, {2000: (1, "2000"), 2001: (2000, "2001\t1")})

    jail, _, processes, directories = _create(root)

    assert jail.channel_namespace_fd is not None
    destroy_jail(jail, processes=processes, directories=directories)
