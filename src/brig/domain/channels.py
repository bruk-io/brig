"""Request channels (decision-0002 item 2): a jail's declared channels, and the
reservation each one gets against the jail's own channel directory.

A reservation is made before the jail's process starts, so an embedder learns each
channel's `endpoint` before it builds the command and writes that endpoint into the
command's argv itself -- never its environment (old SPEC decision-184/186: nothing that
scrubs environment variables can lose an argv entry). Nothing here creates, opens or
checks anything: the directory is a pair of plain strings presentation hands in, and
creating it is infra's (`infra/sockets.py`, TASK-0001.26), the same way `state_dir`
crosses into `compile_supervisor_launch` (rule 2).

`reserve` refuses by returning a value, never by raising (rule 9: only `api` raises);
`presentation/api.py` matches it and raises `ChannelNameRefused` in its place.
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
    """The per-jail channel directory, as each side of the boundary sees it:
    `host_path` where it lives on the host, `jail_path` where the jail type binds it
    inside the jail.

    bwrap binds it at its own host path, so the two are equal there today: a fixed
    in-jail path would need its mountpoint created on `WHOLE_HOST_READ_ONLY`'s
    read-only root, the EROFS TASK-0001.22 measured. They stay two fields because a
    jail type with a different mount layout would make them differ, and because a
    reservation's `bound_path` and `endpoint` are derived one from each.
    """

    host_path: str
    jail_path: str


@dataclass(frozen=True)
class Reservation:
    """One channel's reservation: `bound_path` is the host path of its file in the
    channel directory, `endpoint` the same file's path inside the jail -- the one the
    embedder puts in the jailed command's argv.
    """

    name: str
    bound_path: str
    endpoint: str


@dataclass(frozen=True)
class Reservations:
    """What `reserve` hands back: every declared channel's reservation, in the order
    declared, and the directory they point into -- the directory a jail type's compile
    binds into the jail when `reservations` is not empty.
    """

    directory: ChannelDirectory
    reservations: tuple[Reservation, ...]


@dataclass(frozen=True)
class ChannelRefused:
    """`reserve`'s refusal: `name` would not name exactly one file inside the
    channel directory -- it is empty, `.` or `..`, contains `/` or NUL, or repeats a
    channel declared before it.
    """

    name: str


def _escapes(name: str) -> bool:
    """Whether `name`, joined under a directory, could name anything but a distinct
    file directly inside it: the directory itself (empty, `.`), its parent (`..`), a
    path elsewhere (`/`), or a string the kernel truncates at a NUL.
    """
    return name in ("", ".", "..") or "/" in name or "\0" in name


def _join(directory: str, name: str) -> str:
    """`name` directly under `directory`, by string: domain does no I/O and imports no
    `os.path` (rule 2), and `name` has already been checked not to escape.
    """
    return directory.rstrip("/") + "/" + name


def reserve(
    channels: tuple[Channel, ...], directory: ChannelDirectory
) -> Reservations | ChannelRefused:
    """Reserve each of `channels` in `directory`: its `bound_path` under
    `directory.host_path` and its `endpoint` under `directory.jail_path`, both named
    by the channel's own name.

    Deterministic: the same channels and directory always give the same reservations.
    The first channel whose name would escape the directory, or repeats an earlier
    one, is refused instead, and nothing is reserved.
    """
    seen: set[str] = set()
    for channel in channels:
        if _escapes(channel.name) or channel.name in seen:
            return ChannelRefused(channel.name)
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
