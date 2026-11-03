"""Integration tests for the policy refusal at create (decision-0007): a policy brig cannot
compile fails at `create_bwrap_jail` with brig's own error, before the channel directory or the
supervisor script is written.

These go through the real default `supervisors`/`processes`, so `_supervisors_for` (where the
refusal runs) executes against brig's real state directory. The `directories` port is a fake:
the refusal reads the policy, never the port, so its `created` shows whether the call got that
far.
"""

import pytest
from tests.integration.fakes import FakeChannelDirectories

from brig import (
    WHOLE_HOST_READ_ONLY,
    Channel,
    FsPolicy,
    PolicyMaskHides,
    PolicyPathNotAbsolute,
    create_bwrap_jail,
    reserve_channels,
)


def test_a_mask_hiding_the_channel_directory_is_refused_before_anything_is_created() -> None:
    directories = FakeChannelDirectories(path="/fake/state/channels/0001")
    reserved = reserve_channels((Channel("ctl"),), directories=directories)
    policy = FsPolicy(readable=("/",), masks=("/fake",))

    with pytest.raises(PolicyMaskHides) as exc_info:
        create_bwrap_jail(("true",), policy=policy, channels=reserved, directories=directories)

    assert (exc_info.value.mask, exc_info.value.path) == ("/fake", "/fake/state/channels/0001")
    assert directories.created == []


def test_a_relative_path_is_refused_before_anything_is_created() -> None:
    directories = FakeChannelDirectories(path="/fake/state/channels/0002")
    reserved = reserve_channels((Channel("ctl"),), directories=directories)

    with pytest.raises(PolicyPathNotAbsolute) as exc_info:
        create_bwrap_jail(
            ("true",),
            policy=FsPolicy(readable=("/",), writable=("work",)),
            channels=reserved,
            directories=directories,
        )

    assert exc_info.value.path == "work"
    assert directories.created == []


def test_the_default_policy_is_not_refused_and_reaches_directory_creation() -> None:
    """Control: `WHOLE_HOST_READ_ONLY` with a channel directory under the state directory is the
    common case. Stops once `directories.create` is reached, by failing the create itself, so no
    real bwrap is needed."""
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
