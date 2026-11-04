"""TASK-0001.38: `reserve` measures each endpoint's encoded bytes, NUL included, against the
`sun_path` size it is given, and refuses one that does not fit as a value. The repro is
`test_channels_path_limit_repro.py`; this file pins both sides of the limit.
"""

from brig.domain.channels import (
    SUN_PATH_BYTES_DARWIN,
    SUN_PATH_BYTES_LINUX,
    Channel,
    ChannelDirectory,
    ChannelEndpointRefusal,
    ChannelNameRefusal,
    Reservations,
    reserve,
)


def _directory_for(endpoint_bytes: int, name: str) -> ChannelDirectory:
    """A channel directory, different on each side, under which `name`'s endpoint is exactly
    `endpoint_bytes` long (`/` + padding + `/` + `name`, ASCII padding)."""
    padding = endpoint_bytes - 2 - len(name.encode())
    jail_path = "/" + "j" * padding
    return ChannelDirectory(host_path="/host", jail_path=jail_path)


def test_the_longest_endpoint_that_fits_with_its_nul_is_reserved() -> None:
    """107 bytes and a NUL fill Linux's 108-byte `sun_path` exactly: reserved."""
    result = reserve((Channel("s"),), _directory_for(SUN_PATH_BYTES_LINUX - 1, "s"))

    assert isinstance(result, Reservations)
    assert len(result.reservations[0].endpoint) == SUN_PATH_BYTES_LINUX - 1


def test_one_byte_more_is_refused_naming_the_endpoint_and_the_limit() -> None:
    """108 bytes leave no room for the NUL: refused, with the endpoint, its length and the
    limit."""
    directory = _directory_for(SUN_PATH_BYTES_LINUX, "s")

    result = reserve((Channel("s"),), directory)

    assert result == ChannelEndpointRefusal(
        name="s",
        endpoint=directory.jail_path + "/s",
        length=SUN_PATH_BYTES_LINUX,
        limit=SUN_PATH_BYTES_LINUX,
    )


def test_the_length_is_counted_in_encoded_bytes_not_characters() -> None:
    """A name of 3-byte characters is measured as the kernel sees it: an endpoint of 52
    characters is 112 bytes, and refused."""
    name = "€" * 30  # 90 bytes in UTF-8, 30 characters
    directory = ChannelDirectory(host_path="/host", jail_path="/" + "j" * 20)

    result = reserve((Channel(name),), directory)

    assert isinstance(result, ChannelEndpointRefusal)
    assert result.length == 1 + 20 + 1 + 90


def test_only_the_endpoint_is_measured_never_the_host_path() -> None:
    """The host reaches the socket through an fd, so a long host path alone is reserved."""
    directory = ChannelDirectory(host_path="/" + "h" * 200, jail_path="/jail")

    assert isinstance(reserve((Channel("s"),), directory), Reservations)


def test_the_limit_given_is_the_limit_used() -> None:
    """macOS's 104-byte `sun_path`: an endpoint of 104 bytes fits Linux but not macOS."""
    directory = _directory_for(SUN_PATH_BYTES_DARWIN, "s")

    assert isinstance(reserve((Channel("s"),), directory), Reservations)
    assert isinstance(
        reserve((Channel("s"),), directory, sun_path_bytes=SUN_PATH_BYTES_DARWIN),
        ChannelEndpointRefusal,
    )


def test_a_name_that_escapes_is_refused_before_any_length_is_measured() -> None:
    """A bad name is still the name's refusal, even under a directory too long for any
    endpoint."""
    directory = ChannelDirectory("/" + "a" * 120, "/" + "a" * 120)

    assert reserve((Channel(".."),), directory) == ChannelNameRefusal("..")
