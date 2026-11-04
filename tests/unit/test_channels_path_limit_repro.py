"""TASK-0001.38's repro: `reserve` never checks an endpoint against the AF_UNIX path limit.

`sun_path` holds 108 bytes on Linux, its NUL included, so a jailed program can neither bind nor
connect to a longer path. A channel directory 121 bytes long makes every endpoint under it longer
than that, and `reserve` hands it back as a reservation anyway: nothing says so until the jailed
program fails to listen.
"""

from brig.domain.channels import Channel, ChannelDirectory, Reservations, reserve


def test_an_endpoint_over_the_sun_path_limit_is_not_reserved() -> None:
    """A 123-byte endpoint (`/` + 120 `a` + `/s`) is refused as a value, not reserved."""
    directory = ChannelDirectory("/" + "a" * 120, "/" + "a" * 120)

    result = reserve((Channel("s"),), directory)

    assert not isinstance(result, Reservations)
