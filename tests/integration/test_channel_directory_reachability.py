"""Integration tests for the channel directory's reachability guard (TASK-0001.26
AC#2): a jail that declares channels under an `FsPolicy` that cannot reach the channel
directory fails at create with `ChannelDirectoryUnreachable`, before the directory or
the supervisor script is written.

These go through the real default `supervisors`/`processes`, so `_supervisors_for`
(where the guard runs) actually executes, against brig's real state directory --
`BRIG_HOME` cannot be redirected per test, since the resolved state directory is
cached for the life of the process (`_resolved_state_dir`). The `directories` port is
a fake: the guard reads `policy`, never the port, so asserting on `created` shows
whether the guard let the call through without entangling the test with real bwrap.
"""

from pathlib import Path

import pytest
from tests.integration.fakes import FakeChannelDirectories

from brig import (
    WHOLE_HOST_READ_ONLY,
    Bind,
    Channel,
    ChannelDirectoryUnreachable,
    FsPolicy,
    create_bwrap_jail,
    reserve_channels,
)


def test_a_read_only_ancestor_bind_brig_cannot_write_to_is_refused_before_anything_is_created(
    tmp_path: Path,
) -> None:
    """The channel directory (outside the state directory) sits under a read-only
    bind of the policy's own, sourced from a host path that is not the state
    directory: bwrap could not make its mountpoint, and brig cannot create the leaf
    in a directory it does not own -- refused loudly, with nothing created.
    """
    directories = FakeChannelDirectories(path="/fake/state/channels/0001")
    reserved = reserve_channels((Channel("ctl"),), directories=directories)
    policy = FsPolicy(binds=(Bind(host_path=str(tmp_path), jail_path="/fake"),))

    with pytest.raises(ChannelDirectoryUnreachable) as exc_info:
        create_bwrap_jail(("true",), policy=policy, channels=reserved, directories=directories)

    assert exc_info.value.channel_dir == "/fake/state/channels/0001"
    assert exc_info.value.ancestor == policy.binds[0]
    assert directories.created == []


def test_the_default_policy_does_not_trip_the_guard_and_reaches_directory_creation() -> None:
    """Control: `WHOLE_HOST_READ_ONLY` with a channel directory under the state
    directory (named by the real default allocator, which creates nothing) is the
    common case and must not be refused. Stops once `directories.create` is reached,
    by failing the create itself, so no real bwrap is needed either way.
    """
    reserved = reserve_channels((Channel("ctl"),))
    state_channel = reserved.directory.host_path
    directories = FakeChannelDirectories(path=state_channel)

    class _Stop(Exception):
        pass

    def stop(path: str) -> None:
        directories.created.append(path)
        raise _Stop

    directories.create = stop  # type: ignore[method-assign]

    with pytest.raises(_Stop):
        create_bwrap_jail(
            ("true",), policy=WHOLE_HOST_READ_ONLY, channels=reserved, directories=directories
        )

    assert directories.created == [state_channel]
