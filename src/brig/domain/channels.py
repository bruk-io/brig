"""Request channels (decision-0002 item 2): a jail's declared channels, and each one's
reservation in the jail's channel directory.

A reservation is made before the jail starts, so the embedder writes each `endpoint` into the
command's argv, never its environment (old SPEC decision-184/186: no environment scrubbing can
lose an argv entry). Nothing here touches the filesystem; `reserve` refuses by returning a value
(rule 9), a name that escapes the directory and an endpoint too long for `sun_path` alike.
"""

from dataclasses import dataclass

SUN_PATH_BYTES_LINUX = 108
"""The size of `sockaddr_un.sun_path` on Linux, its terminating NUL included: the longest
endpoint a jailed program can bind or connect to is one byte shorter. A domain constant, since
the domain may not import `socket` (rule 2)."""

SUN_PATH_BYTES_DARWIN = 104
"""`sockaddr_un.sun_path` on macOS, its NUL included."""


@dataclass(frozen=True)
class Channel:
    """A channel an embedder declares for its jail, by name: one file in the jail's
    channel directory, usually a socket its jailed command listens on.
    """

    name: str


@dataclass(frozen=True)
class ChannelDirectory:
    """The per-jail channel directory: `host_path` on the host, `jail_path` inside the jail.
    bwrap binds it at its host path, so the two are equal there (a fixed in-jail path would
    need a mountpoint on a read-only root: EROFS, TASK-0001.22)."""

    host_path: str
    jail_path: str


@dataclass(frozen=True)
class Reservation:
    """One channel's reservation: `bound_path`, its file's host path, and `endpoint`, the same
    file's path inside the jail, which the embedder puts in the command's argv. The embedder
    never dials `bound_path`: the jail can write what is there, a link to a host socket
    included, so it talks over the connection readiness verified (TASK-0001.34)."""

    name: str
    bound_path: str
    endpoint: str


@dataclass(frozen=True)
class Reservations:
    """Every declared channel's reservation, in declared order, and the directory a jail type
    binds into the jail when there is at least one."""

    directory: ChannelDirectory
    reservations: tuple[Reservation, ...]


@dataclass(frozen=True)
class ChannelNameRefusal:
    """`reserve`'s refusal: `name` would not name exactly one file inside the channel
    directory (empty, `.` or `..`, containing `/` or NUL, or a repeat)."""

    name: str


@dataclass(frozen=True)
class ChannelEndpointRefusal:
    """`reserve`'s refusal: `endpoint`, the channel `name`'s path inside the jail, is
    `length` bytes encoded, so with its NUL it does not fit the `limit`-byte `sun_path` a
    program binds it through."""

    name: str
    endpoint: str
    length: int
    limit: int


def _escapes(name: str) -> bool:
    """Whether `name`, joined under a directory, could name anything but a distinct file
    directly inside it."""
    return name in ("", ".", "..") or "/" in name or "\0" in name


def _join(directory: str, name: str) -> str:
    """`name` directly under `directory`, by string (no `os.path` in the domain, rule 2)."""
    return directory.rstrip("/") + "/" + name


def _encoded_length(path: str) -> int:
    """`path`'s length in bytes as the host's filesystem encoding gives it to the kernel (UTF-8,
    an undecodable byte carried as a lone surrogate)."""
    return len(path.encode("utf-8", "surrogateescape"))


def reserve(
    channels: tuple[Channel, ...],
    directory: ChannelDirectory,
    *,
    sun_path_bytes: int = SUN_PATH_BYTES_LINUX,
) -> Reservations | ChannelNameRefusal | ChannelEndpointRefusal:
    """Reserve each of `channels` in `directory`, named by the channel's name; deterministic.
    The first name that would escape the directory or repeats an earlier one is refused, and
    nothing is reserved. So is the first endpoint that does not fit, NUL included, in a
    `sun_path` of `sun_path_bytes` (the platform's: `SUN_PATH_BYTES_LINUX` by default), since
    no program could bind or connect to it (TASK-0001.38). Only the endpoint is measured: the
    host reaches the socket through an fd, never by its `bound_path`."""
    seen: set[str] = set()
    for channel in channels:
        if _escapes(channel.name) or channel.name in seen:
            return ChannelNameRefusal(channel.name)
        seen.add(channel.name)
    reservations = tuple(
        Reservation(
            name=channel.name,
            bound_path=_join(directory.host_path, channel.name),
            endpoint=_join(directory.jail_path, channel.name),
        )
        for channel in channels
    )
    for reservation in reservations:
        length = _encoded_length(reservation.endpoint)
        if length >= sun_path_bytes:
            return ChannelEndpointRefusal(
                reservation.name, reservation.endpoint, length, sun_path_bytes
            )
    return Reservations(directory=directory, reservations=reservations)
