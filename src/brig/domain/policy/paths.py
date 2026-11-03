"""Which paths a jail may read and write: what the embedder means, not how a jail type
mounts it (decision-0007). Plain data and the pure checks over it (rule 2). Each jail type's
compile turns an `FsPolicy` into its own mechanism: bwrap's into an ordered tuple of mounts
(`domain/jail_types/bwrap.py`).

Every path is absolute and names the same place inside the jail as on the host. Where two
entries overlap, the more specific path wins: a write deny inside a writable root is
read-only, a mask inside a readable root is unreadable.
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class FsPolicy:
    """What a jail's command may see of the host's filesystem.

    `readable`: roots the command may read and not write. `writable`: roots it may read and
    write. `write_denies`: paths inside a writable root it may read and not write (an absent
    one it may not create). `masks`: paths it may not read, write or create, wherever they
    are. Nothing outside the roots exists in the jail.
    """

    readable: tuple[str, ...] = ()
    writable: tuple[str, ...] = ()
    write_denies: tuple[str, ...] = ()
    masks: tuple[str, ...] = ()


WHOLE_HOST_READ_ONLY = FsPolicy(readable=("/",))
"""The default: the whole host, read-only, nothing writable and nothing masked."""


class PathKind(StrEnum):
    """What is at a write deny's or a mask's path on the host when a jail is compiled: the
    one host fact a compile needs (rule 2: presentation looks, the domain decides)."""

    FILE = "file"
    DIRECTORY = "directory"
    ABSENT = "absent"


@dataclass(frozen=True)
class PathNotAbsolute:
    """A refusal: `path` in the policy is not absolute and normalised."""

    path: str


@dataclass(frozen=True)
class MaskHides:
    """A refusal: `mask` hides `path`, which the jail needs to see: a root of the policy, or
    brig's own state or channel directory."""

    mask: str
    path: str


def _is_normal_absolute(path: str) -> bool:
    if not path.startswith("/") or "//" in path:
        return False
    parts = path.split("/")[1:]
    return path == "/" or all(part not in {"", ".", ".."} for part in parts)


def within(path: str, root: str) -> bool:
    """Whether `path` is `root` or beneath it, comparing whole components."""
    return path == root or root == "/" or path.startswith(root + "/")


def refusal(policy: FsPolicy, needed: tuple[str, ...] = ()) -> PathNotAbsolute | MaskHides | None:
    """Why `policy` cannot be compiled, or `None`. `needed` are the paths the jail must see
    for brig's own sake (its state directory, a channel directory), refused under a mask the
    same way a root is.

    A mask can only hide: a root, or a path brig needs, at or beneath a mask would be mounted
    inside an empty read-only directory, where nothing can be made to mount it on.
    """
    every = (*policy.readable, *policy.writable, *policy.write_denies, *policy.masks, *needed)
    for path in every:
        if not _is_normal_absolute(path):
            return PathNotAbsolute(path)
    for mask in policy.masks:
        for path in (*policy.readable, *policy.writable, *needed):
            if within(path, mask):
                return MaskHides(mask, path)
    return None
