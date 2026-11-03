"""Which paths a jail may read and write: what the embedder means, not how a jail type
mounts it (decision-0007). Plain data and the pure checks over it (rule 2). Each jail type's
compile turns an `FsPolicy` into its own mechanism: bwrap's into an ordered tuple of mounts
(`domain/jail_types/bwrap.py`).

Every path is absolute and names the same place inside the jail as on the host. Where two
entries overlap, the more specific path wins: a write deny inside a writable root is
read-only, a mask inside a readable root is unreadable.
"""

from collections.abc import Mapping
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
class HostPath:
    """What presentation found at a policy path on the host: its kind, and where it resolves to
    once every symbolic link on the way is followed (`os.path.realpath`)."""

    kind: PathKind
    resolved: str


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


@dataclass(frozen=True)
class RootAbsent:
    """A refusal: the readable or writable root `path` does not exist on the host."""

    path: str


@dataclass(frozen=True)
class ThroughLink:
    """A refusal: `path` is reached through a symbolic link inside the writable root `root`. The
    command may replace that link, and a mount follows it, so nothing at `path` would hold."""

    path: str
    root: str


@dataclass(frozen=True)
class CwdOutsideRoots:
    """A refusal: the command's working directory `cwd` is in no root of the policy, so it does
    not exist in the jail."""

    cwd: str


@dataclass(frozen=True)
class StdioInWritableRoot:
    """A refusal: the stdio path `path` is inside a writable root, where a jail could replace it
    with a link to any file the embedder can write (TASK-0031)."""

    path: str


@dataclass(frozen=True)
class InterpreterUnreachable:
    """A refusal: `path`, on the way to the interpreter brig runs its supervisor under, is in no
    root of the policy (or under a mask), so the supervisor could not start (TASK-0029)."""

    path: str


def _is_normal_absolute(path: str) -> bool:
    if not path.startswith("/") or "//" in path:
        return False
    parts = path.split("/")[1:]
    return path == "/" or all(part not in {"", ".", ".."} for part in parts)


def within(path: str, root: str) -> bool:
    """Whether `path` is `root` or beneath it, comparing whole components."""
    return path == root or root == "/" or path.startswith(root + "/")


def _reached_through_link(path: str, root: str, host: Mapping[str, HostPath]) -> bool:
    """Whether `path`, inside `root`, resolves anywhere but where `root` resolves plus the rest of
    `path`: a link sits between them."""
    found, base = host.get(path), host.get(root)
    if found is None or base is None:
        return False
    rest = path if root == "/" else path[len(root) :]
    return found.resolved != base.resolved.rstrip("/") + rest


def refusal(
    policy: FsPolicy,
    needed: tuple[str, ...] = (),
    host: Mapping[str, HostPath] | None = None,
) -> PathNotAbsolute | MaskHides | RootAbsent | ThroughLink | None:
    """Why `policy` cannot be compiled, or `None`. `needed` are the paths the jail must see for
    brig's own sake (its state directory, a channel directory), refused under a mask the same way
    a root is. `host` is what presentation found at each policy path; without it, only what the
    policy says alone is checked.

    A mask can only hide: a root, or a path brig needs, beneath a mask would be mounted inside an
    empty read-only directory. A root must exist to be mounted. And no entry may be reached through
    a symbolic link inside a writable root: the command could replace the link, and a mount onto a
    link lands on its target, so the entry would protect the target and not the path.
    """
    every = (*policy.readable, *policy.writable, *policy.write_denies, *policy.masks, *needed)
    for path in every:
        if not _is_normal_absolute(path):
            return PathNotAbsolute(path)
    for mask in policy.masks:
        for path in (*policy.readable, *policy.writable, *needed):
            if within(path, mask):
                return MaskHides(mask, path)
    known = host or {}
    for root in (*policy.readable, *policy.writable):
        if root in known and known[root].kind is PathKind.ABSENT:
            return RootAbsent(root)
    entries = (*policy.readable, *policy.writable, *policy.write_denies, *policy.masks)
    for root in policy.writable:
        for path in entries:
            if path != root and within(path, root) and _reached_through_link(path, root, known):
                return ThroughLink(path, root)
    return None


def cwd_refusal(policy: FsPolicy, cwd: str) -> PathNotAbsolute | CwdOutsideRoots | MaskHides | None:
    """Why `cwd` cannot be the command's working directory under `policy`, or `None`: it must be
    absolute and normalised, inside a readable or writable root, and under no mask."""
    if not _is_normal_absolute(cwd):
        return PathNotAbsolute(cwd)
    if not any(within(cwd, root) for root in (*policy.readable, *policy.writable)):
        return CwdOutsideRoots(cwd)
    for mask in policy.masks:
        if within(cwd, mask):
            return MaskHides(mask, cwd)
    return None


def stdio_refusal(
    policy: FsPolicy, streams: tuple[str | None, ...]
) -> PathNotAbsolute | StdioInWritableRoot | None:
    """Why the stdio paths `streams` cannot be used with `policy`, or `None`: each named one must
    be absolute and outside every writable root (`"/dev/null"` is always fine)."""
    for path in streams:
        if path is None or path == "/dev/null":
            continue
        if not _is_normal_absolute(path):
            return PathNotAbsolute(path)
        if any(within(path, root) for root in policy.writable):
            return StdioInWritableRoot(path)
    return None


def interpreter_refusal(policy: FsPolicy, chain: tuple[str, ...]) -> InterpreterUnreachable | None:
    """Why the supervisor's interpreter cannot run under `policy`, or `None`. `chain` is every
    path met on the way to it, the interpreter's own first and each link's target after it
    (`infra/files.py`'s `link_chain`): each must be inside a root and under no mask, since a
    mount shows a link's target only where the link itself is mounted too."""
    roots = (*policy.readable, *policy.writable)
    for path in chain:
        inside = any(within(path, root) for root in roots)
        if not inside or any(within(path, mask) for mask in policy.masks):
            return InterpreterUnreachable(path)
    return None
