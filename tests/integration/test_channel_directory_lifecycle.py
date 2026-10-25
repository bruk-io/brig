"""Integration tests for the per-jail channel directory's lifecycle (TASK-0001.26
AC#3): through brig's public API, with the world faked at infra's edge, the channel
directory `create_bwrap_jail` creates is gone after `destroy_jail`, after a
`create_bwrap_jail` that fails once the directory exists, and after a jail destroyed
before it ever ran.

`FakeChannelDirectories` records `created`/`removed`, so each assertion reads the
exact path brig asked the world to create and remove.
"""

import pytest
from tests.integration.fakes import FakeChannelDirectories, FakeProcesses, FakeSupervisors

from brig import (
    Channel,
    JailSpawnFailed,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
    run_jail,
)


def test_the_channel_directory_is_created_before_start_and_removed_after_destroy() -> None:
    """An ordinary create, run and destroy: `created` names the directory when the
    jail is created, `removed` names the same path only after `destroy_jail`.
    """
    directories = FakeChannelDirectories()
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    reserved = reserve_channels((Channel("ctl"),), directories=directories)

    jail = create_bwrap_jail(
        ("server",),
        channels=reserved,
        processes=processes,
        supervisors=supervisors,
        directories=directories,
    )
    assert directories.created == [directories.path]
    assert directories.removed == []
    run_jail(jail, processes=processes)
    assert directories.removed == []
    destroy_jail(jail, processes=processes, directories=directories)

    assert directories.removed == [directories.path]


def test_the_channel_directory_is_removed_when_a_jail_is_destroyed_before_it_ever_ran() -> None:
    """`run_jail` never ran; `destroy_jail` still removes the directory, because
    `channel_directory` rides on the `Jail` itself.
    """
    directories = FakeChannelDirectories()
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    reserved = reserve_channels((Channel("ctl"),), directories=directories)
    jail = create_bwrap_jail(
        ("server",),
        channels=reserved,
        processes=processes,
        supervisors=supervisors,
        directories=directories,
    )

    destroy_jail(jail, processes=processes, directories=directories)

    assert supervisors.awaited == []
    assert directories.removed == [directories.path]


def test_the_channel_directory_is_removed_when_create_fails_after_it_exists() -> None:
    """The supervisor refuses to start, so `create_bwrap_jail` raises
    `JailSpawnFailed` -- after `created` already names the directory and with no
    `Jail` to hand `destroy_jail` -- and the directory is removed before the raise.
    """
    directories = FakeChannelDirectories()
    reserved = reserve_channels((Channel("ctl"),), directories=directories)

    with pytest.raises(JailSpawnFailed):
        create_bwrap_jail(
            ("server",),
            channels=reserved,
            processes=FakeProcesses(),
            supervisors=FakeSupervisors(fail_start=True),
            directories=directories,
        )

    assert directories.created == [directories.path]
    assert directories.removed == [directories.path]


def test_a_jail_declaring_no_channel_creates_and_removes_nothing() -> None:
    """No channels, no directory: neither call reaches the port."""
    directories = FakeChannelDirectories()
    processes = FakeProcesses()
    jail = create_bwrap_jail(
        ("true",),
        processes=processes,
        supervisors=FakeSupervisors(),
        directories=directories,
    )

    destroy_jail(jail, processes=processes, directories=directories)

    assert directories.created == []
    assert directories.removed == []
