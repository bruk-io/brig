"""TASK-0001.38 AC#3: through brig's public API, a channel directory long enough that an
endpoint cannot fit AF_UNIX's `sun_path` makes `reserve_channels` raise a typed error naming the
endpoint and saying what to shorten, before anything is made on the host.

`FakeChannelDirectories` stands in for brig's state directory with a long `path`, as a long
`BRIG_HOME` would give; its `created` says nothing was made.
"""

import pytest
from tests.integration.fakes import FakeChannelDirectories

from brig import Channel, ChannelEndpointTooLong, reserve_channels


def test_an_endpoint_too_long_for_sun_path_is_refused_saying_what_to_shorten() -> None:
    """A 121-byte channel directory gives `ctl` a 125-byte endpoint: refused, the error naming
    the endpoint, its length, `BRIG_HOME` and the channel name, and nothing created."""
    directories = FakeChannelDirectories(path="/" + "a" * 120)

    with pytest.raises(ChannelEndpointTooLong) as raised:
        reserve_channels((Channel("ctl"),), directories=directories)

    message = str(raised.value)
    assert raised.value.endpoint == directories.path + "/ctl"
    assert raised.value.length == 125
    assert directories.path + "/ctl" in message
    assert "shorten BRIG_HOME" in message
    assert "channel name" in message
    assert directories.created == []


def test_the_same_channel_under_a_short_directory_is_reserved() -> None:
    """The positive control: the same channel under a short directory is reserved."""
    directories = FakeChannelDirectories()

    reserved = reserve_channels((Channel("ctl"),), directories=directories)

    assert reserved.reservations[0].endpoint == directories.path + "/ctl"
