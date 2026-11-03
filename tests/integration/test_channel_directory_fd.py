"""TASK-0045: the fd a channel-declaring jail holds on its channel directory, for readiness to
open each channel's name beneath, lives exactly as long as the jail. `create_bwrap_jail` opens
it right after the directory is made and puts it on the `Jail`; `destroy_jail` closes it, and a
create that fails once it is open closes it through the same cleanup (TASK-0044).

The world is faked at infra's edge: `FakeChannelDirectories` makes its directory under a
throwaway root, so the fd is a real one on a real directory, and this test reads the process's
own `/proc/self/fd` to see what is still open.
"""

import os
import stat
from pathlib import Path

import pytest
from tests.integration.fakes import (
    FakeChannelDirectories,
    FakeProcesses,
    FakeSupervisors,
    plant_fake_proc,
)

from brig import (
    Channel,
    ChannelNamespaceNotFound,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
)


def _open_fds() -> frozenset[str]:
    """This process's open fds, as `/proc/self/fd` lists them."""
    return frozenset(os.listdir("/proc/self/fd"))


def test_the_jail_holds_an_fd_on_its_channel_directory_until_destroy(tmp_path: Path) -> None:
    """The `Jail` carries an open fd on the very directory that was made, and after
    `destroy_jail` no fd the create opened is left."""
    proc_root = str(tmp_path / "proc")
    plant_fake_proc(proc_root, {2000: (1, "2000"), 2001: (2000, "2001\t1")})
    directories = FakeChannelDirectories()
    processes = FakeProcesses()
    before = _open_fds()

    jail = create_bwrap_jail(
        ("server",),
        channels=reserve_channels((Channel("ctl"),), directories=directories),
        processes=processes,
        supervisors=FakeSupervisors(),
        directories=directories,
        proc_root=proc_root,
    )
    assert jail.channel_directory_fd is not None
    held = os.fstat(jail.channel_directory_fd)
    made = os.stat(directories.path)
    destroy_jail(jail, processes=processes, directories=directories)

    assert stat.S_ISDIR(held.st_mode)
    assert (held.st_dev, held.st_ino) == (made.st_dev, made.st_ino)
    assert _open_fds() == before


def test_a_create_that_fails_after_the_open_closes_the_fd(tmp_path: Path) -> None:
    """The namespace scan fails once the directory fd is open: the create's cleanup closes it,
    so nothing the create opened is left."""
    directories = FakeChannelDirectories()
    before = _open_fds()

    with pytest.raises(ChannelNamespaceNotFound):
        create_bwrap_jail(
            ("server",),
            channels=reserve_channels((Channel("ctl"),), directories=directories),
            processes=FakeProcesses(),
            supervisors=FakeSupervisors(),
            directories=directories,
            proc_root=str(tmp_path / "no-proc-here"),
        )

    assert directories.removed == [directories.path]
    assert _open_fds() == before
