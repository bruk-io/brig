"""Request channels (decision-0002 item 2): a jail's declared channels, and each one's
reservation in the jail's channel directory.

A reservation is made before the jail starts, so the embedder writes each `endpoint` into the
command's argv, never its environment (old SPEC decision-184/186: no environment scrubbing can
lose an argv entry). Nothing here touches the filesystem; `reserve` refuses by returning a value
(rule 9).
"""

from dataclasses import dataclass


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
    file's path inside the jail, which the embedder puts in the command's argv."""

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


def _escapes(name: str) -> bool:
    """Whether `name`, joined under a directory, could name anything but a distinct file
    directly inside it."""
    return name in ("", ".", "..") or "/" in name or "\0" in name


def _join(directory: str, name: str) -> str:
    """`name` directly under `directory`, by string (no `os.path` in the domain, rule 2)."""
    return directory.rstrip("/") + "/" + name


def reserve(
    channels: tuple[Channel, ...], directory: ChannelDirectory
) -> Reservations | ChannelNameRefusal:
    """Reserve each of `channels` in `directory`, named by the channel's name; deterministic.
    The first name that would escape the directory or repeats an earlier one is refused, and
    nothing is reserved."""
    seen: set[str] = set()
    for channel in channels:
        if _escapes(channel.name) or channel.name in seen:
            return ChannelNameRefusal(channel.name)
        seen.add(channel.name)
    return Reservations(
        directory=directory,
        reservations=tuple(
            Reservation(
                name=channel.name,
                bound_path=_join(directory.host_path, channel.name),
                endpoint=_join(directory.jail_path, channel.name),
            )
            for channel in channels
        ),
    )
