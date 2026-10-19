"""Unit tests for `domain/channels.py`'s `reserve` (TASK-0001.25 AC#1): each
reservation's `bound_path` and `endpoint` are derived deterministically from the
channel's name and the per-jail channel directory, and a name that would escape the
directory is refused, as a value.
"""

import pytest

from brig.domain.channels import (
    Channel,
    ChannelDirectory,
    ChannelRefused,
    Reservation,
    Reservations,
    reserve,
)

_DIRECTORY = ChannelDirectory(host_path="/host/state/channels/abc", jail_path="/in-jail/ch")
"""Two different strings on purpose: bwrap binds the directory at its own host path, so
in practice they are equal, and a test feeding equal strings could not tell `endpoint`
from `bound_path` if the derivation swapped them.
"""


def test_reserve_derives_bound_path_from_the_host_side_and_endpoint_from_the_jail_side() -> None:
    """Each channel's `bound_path` sits under `host_path` and its `endpoint` under
    `jail_path`, both named by the channel, in the order declared.
    """
    result = reserve((Channel("ctl"), Channel("data")), _DIRECTORY)

    assert result == Reservations(
        directory=_DIRECTORY,
        reservations=(
            Reservation(
                name="ctl", bound_path="/host/state/channels/abc/ctl", endpoint="/in-jail/ch/ctl"
            ),
            Reservation(
                name="data",
                bound_path="/host/state/channels/abc/data",
                endpoint="/in-jail/ch/data",
            ),
        ),
    )


def test_reserve_is_deterministic() -> None:
    """The same channels and directory always give equal reservations."""
    channels = (Channel("ctl"), Channel("data"))

    assert reserve(channels, _DIRECTORY) == reserve(channels, _DIRECTORY)


def test_reserve_joins_under_a_directory_given_with_a_trailing_slash() -> None:
    """A trailing `/` on either side does not double the separator."""
    directory = ChannelDirectory(host_path="/host/ch/", jail_path="/jail/ch/")

    result = reserve((Channel("ctl"),), directory)

    assert isinstance(result, Reservations)
    assert result.reservations == (
        Reservation(name="ctl", bound_path="/host/ch/ctl", endpoint="/jail/ch/ctl"),
    )


def test_reserve_with_no_channels_reserves_nothing() -> None:
    """Declaring no channel gives an empty reservation set, not a refusal."""
    assert reserve((), _DIRECTORY) == Reservations(directory=_DIRECTORY, reservations=())


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../escape", "a/b", "/etc/passwd", "ctl\0x"],
)
def test_reserve_refuses_a_name_that_would_escape_the_directory(name: str) -> None:
    """A name that would name the directory itself, its parent, a path elsewhere, or a
    string the kernel truncates at NUL is refused, and nothing is reserved -- even
    when a valid channel was declared before it.
    """
    assert reserve((Channel("ok"), Channel(name)), _DIRECTORY) == ChannelRefused(name)


def test_reserve_refuses_a_repeated_name() -> None:
    """Two channels with one name would share one file; the second is refused."""
    assert reserve((Channel("ctl"), Channel("ctl")), _DIRECTORY) == ChannelRefused("ctl")
