"""The bwrap jail type's compile: pure, from a request to the argv that starts the jail's
supervisor (decision-0001 rule 3; decision-0002).

`compile_mounts` turns the embedder's `FsPolicy` (intent: readable and writable roots, write
denies, masks; decision-0007) into an ordered tuple of `Mount`s, and everything else about the
jail's filesystem is read from that one tuple: `render` makes bwrap's flags from it, and
`writable_shared_paths` grades `CHANNEL_EXCLUSIVITY_CLAIM` from it. No second reader rebuilds
the order by hand.

The order is the policy's meaning. Entries mount shallowest path first, so the more specific one
wins where two overlap (bwrap applies mounts in argv order; a later mount replaces the view beneath
it). Among them are the pins (TASK-0001.31, old SPEC decision-168): each directory strictly between
a writable root and a write deny, a mask or a readable root nested in it (TASK-0001.33), bound
writable over itself, so the command cannot rename it (a mount point inside the jail's mount
namespace refuses `rename(2)` with `EBUSY`) and take what it leads to with it. Then brig's own: an
empty tmpfs over its state directory, with this jail's supervisor script and channel directory bound
back inside it, the tmpfs remounted read-only (TASK-0019: the directory holds every jail's scripts
and channels, and a Unix socket accepts a connect through a read-only mount); then the virtual
filesystems and the namespace flags.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from brig.domain.channels import Reservations
from brig.domain.claims import Claim
from brig.domain.grades import Grade, at_most
from brig.domain.plan import Plan
from brig.domain.policy.paths import FsPolicy, PathKind, within

_VIRTUAL_FS_FLAGS: tuple[str, ...] = ("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/sys")
"""A procfs of the jail's own PID namespace, a minimal `/dev`, and an empty `/sys`, whatever the
policy binds (decision-0004): a bind of `/` otherwise carries the host's own `/proc` (every host
pid) and `/sys` into the jail. sysfs has no per-namespace view, so it is emptied; an embedder
that needs it binds it back."""

_NAMESPACE_FLAGS: tuple[str, ...] = (
    "--unshare-all",
    "--die-with-parent",
    "--new-session",
    "--cap-drop",
    "ALL",
    "--as-pid-1",
    "--",
)
"""The namespace flags, after the mounts and before the supervisor's argv. Each is load-bearing:

- `--cap-drop ALL` (decision-0006): bwrap run by root drops no capability, and
  `CAP_SYS_PTRACE` would let the command reach its non-dumpable PID 1.
- `--as-pid-1`: without it bwrap puts a reaper of its own at PID 1 and the supervisor at
  PID 3 (measured, TASK-0001.15), so orphans reparent to bwrap's reaper, not the supervisor.
- `--new-session` closes the TIOCSTI escape (TASK-0001.05). uv's managed CPython is built
  without `posix_spawn`'s `setsid` (TASK-0001.12), so where infra's spawn reports
  `session_detached` `False` this flag is the only thing closing it.
"""


def compile_run(command: tuple[str, ...], env: Mapping[str, str] = frozendict()) -> Plan:
    """The plan for running `command`, with `env` as its candidate environment, as the
    supervisor's child (decision-0002). A policy is refused before this, by `refusal`."""
    return Plan(argv=command, env=frozendict(env))


class MountKind(StrEnum):
    """One bwrap mount operation."""

    READ_ONLY = "--ro-bind"
    WRITABLE = "--bind"
    TMPFS = "--tmpfs"
    REMOUNT_READ_ONLY = "--remount-ro"


@dataclass(frozen=True)
class Mount:
    """One mount, in argv order: `source` (a host path) mounted at `target`, or, for a tmpfs
    or a remount, `target` alone."""

    kind: MountKind
    target: str
    source: str = ""


_DEV_NULL = "/dev/null"
"""What a masked file is replaced with: reads are empty and writes refused, read-only."""

_RANK = frozendict({"readable": 0, "writable": 1, "pin": 1, "deny": 2, "mask": 3})
"""At one path, which entry mounts last and so wins: a mask over a deny over a writable root
over a readable one. A pin is never at an entry's path, and binds like a writable root."""


def _depth(path: str) -> int:
    return 0 if path == "/" else path.count("/")


def _governing_role(policy: FsPolicy, path: str) -> str | None:
    """The role of the most specific entry strictly above `path` (at one path, the one that
    mounts last), or `None` when no entry covers it: what the jail shows at `path`'s parent."""
    above = [
        (role, root)
        for role, roots in (
            ("readable", policy.readable),
            ("writable", policy.writable),
            ("deny", policy.write_denies),
            ("mask", policy.masks),
        )
        for root in roots
        if root != path and within(path, root)
    ]
    if not above:
        return None
    return max(above, key=lambda entry: (_depth(entry[1]), _RANK[entry[0]]))[0]


def _entries(policy: FsPolicy) -> frozenset[str]:
    return frozenset((*policy.readable, *policy.writable, *policy.write_denies, *policy.masks))


def _between(path: str, roots: tuple[str, ...]) -> tuple[str, ...]:
    """The directories strictly between `path` and each of `roots` it is inside, shallowest
    first."""
    parts = path.split("/")
    ancestors = ["/".join(parts[:depth]) for depth in range(2, len(parts))]
    return tuple(
        ancestor
        for ancestor in ancestors
        if any(ancestor != root and within(ancestor, root) for root in roots)
    )


def pin_candidates(policy: FsPolicy) -> tuple[str, ...]:
    """Every path strictly between a writable root and a write deny, a mask or a readable root
    inside it: where `compile_mounts` may pin a directory, so what presentation looks up on the
    host for it."""
    return tuple(
        dict.fromkeys(
            ancestor
            for path in (*policy.readable, *policy.write_denies, *policy.masks)
            for ancestor in _between(path, policy.writable)
        )
    )


def _pins(
    policy: FsPolicy, kinds: Mapping[str, PathKind], protected: list[tuple[str, bool]]
) -> set[tuple[str, str]]:
    """The directories to pin on the way to each `protected` `(path, made)`, as `("pin", path)`:
    `made` when brig makes the directories missing on the way to `path` before the jail starts
    (an absent deny or mask, its placeholders); never for a readable root, which exists.

    One is pinned where the jail shows it writable (the most specific entry above it is a
    writable root), it is no entry of the policy (an entry is a mount point already), and it is a
    directory when the jail starts: one on the host, or one brig makes then. One absent on the
    way to an entry that exists is not there to pin.
    """
    entries = _entries(policy)
    pins: set[tuple[str, str]] = set()
    for path, made in protected:
        for directory in _between(path, policy.writable):
            kind = kinds.get(directory, PathKind.ABSENT)
            there = kind is PathKind.DIRECTORY or (made and kind is PathKind.ABSENT)
            if (
                there
                and directory not in entries
                and _governing_role(policy, directory) == "writable"
            ):
                pins.add(("pin", directory))
    return pins


def _kept(policy: FsPolicy, kinds: Mapping[str, PathKind]) -> list[tuple[str, str]]:
    """The policy's entries that need a mount, as `(role, path)`, and the pins on the way to
    each readable root, deny and mask among them (`_pins`).

    A write deny or mask at an absent path needs one only where its parent is writable in the
    jail (the most specific entry above it is a writable root): there the command could create
    it; anywhere else nothing in the jail can, and bwrap could not make its mountpoint on a
    read-only mount either. A deny or mask beneath a mask is hidden already. A write deny outside
    every writable root is read-only already.
    """
    entries = [("readable", p) for p in policy.readable]
    entries += [("writable", p) for p in policy.writable]
    protected = [(path, False) for path in policy.readable]
    for role, paths in (("deny", policy.write_denies), ("mask", policy.masks)):
        for path in paths:
            if any(other != path and within(path, other) for other in policy.masks):
                continue
            if role == "deny" and not any(within(path, root) for root in policy.writable):
                continue
            absent = kinds.get(path, PathKind.ABSENT) is PathKind.ABSENT
            if absent and _governing_role(policy, path) != "writable":
                continue
            entries.append((role, path))
            protected.append((path, absent))
    kept = {*entries, *_pins(policy, kinds, protected)}
    return sorted(kept, key=lambda entry: (_depth(entry[1]), _RANK[entry[0]], entry[1]))


def _mount_for(role: str, path: str, kind: PathKind, empty_dir: str) -> Mount:
    match role:
        case "readable" | "deny":
            source = empty_dir if kind is PathKind.ABSENT and role == "deny" else path
            return Mount(MountKind.READ_ONLY, path, source)
        case "writable" | "pin":
            return Mount(MountKind.WRITABLE, path, path)
        case _:
            source = _DEV_NULL if kind is PathKind.FILE else empty_dir
            return Mount(MountKind.READ_ONLY, path, source)


def compile_mounts(
    policy: FsPolicy,
    kinds: Mapping[str, PathKind],
    *,
    state_dir: str,
    supervisor_script: str,
    empty_dir: str,
    channels: Reservations | None = None,
) -> tuple[Mount, ...]:
    """Every mount a bwrap jail for `policy` needs, in argv order.

    `kinds` is what is at each write deny's and mask's path on the host, and at each of
    `pin_candidates` (presentation looks; a path it does not name reads as absent). `empty_dir`
    is an empty, read-only host directory brig owns: the source for a masked directory, and for
    a deny or mask at an absent path, so the command can neither read nor create anything there.
    `refusal` in `domain/policy/paths.py` must have passed first.
    """
    mounts = [
        _mount_for(role, path, kinds.get(path, PathKind.ABSENT), empty_dir)
        for role, path in _kept(policy, kinds)
    ]
    mounts.append(Mount(MountKind.TMPFS, state_dir))
    mounts.append(Mount(MountKind.READ_ONLY, supervisor_script, supervisor_script))
    if channels is not None and channels.reservations:
        directory = channels.directory.host_path
        mounts.append(Mount(MountKind.WRITABLE, directory, directory))
    mounts.append(Mount(MountKind.REMOUNT_READ_ONLY, state_dir))
    return tuple(mounts)


def render(mounts: tuple[Mount, ...]) -> tuple[str, ...]:
    """bwrap's flags for `mounts`, in order."""
    flags: list[str] = []
    for mount in mounts:
        match mount.kind:
            case MountKind.TMPFS | MountKind.REMOUNT_READ_ONLY:
                flags += [mount.kind.value, mount.target]
            case MountKind.READ_ONLY | MountKind.WRITABLE:
                flags += [mount.kind.value, mount.source, mount.target]
    return tuple(flags)


CHANNEL_EXCLUSIVITY_CLAIM = Claim(
    name="channel_exclusivity",
    description=(
        "the only paths this jail can write that the host can also reach are the channels it "
        "declared, and the only host paths it sees are its own channel directory and brig's own "
        "mounts, so it can dial no socket the host keeps: nothing crosses the boundary "
        "anonymously (law 9). A readable or writable root shows the jail host directories where "
        "a socket could sit, and no list of places finds every one, so any root makes this at "
        "best best-effort: it holds until the host puts a listening socket under a root; one of "
        "the places hosts keep sockets in (/run, /tmp and the like) visible, or a writable "
        "root, violates it. Stdio is no shared path: the command's fd 0, 1 and 2 are pipes the "
        "host pumps, carrying only the bytes the embedder sends in and the command writes out, "
        "never a host file the jail could reopen"
    ),
)
"""What the compile claims about the paths it mounts (law 9). A claim, never a grade:
`domain/grades.py`'s `grade` decides that from evidence a battery measured."""


FS_WRITE_CLAIM = Claim(
    name="fs_write",
    description=(
        "the command writes only inside the policy's writable roots and its declared channels, "
        "and nothing a write deny names; nor can it rename a directory on the way to a write "
        "deny, a mask or a readable root inside a writable root that was there when the jail "
        "started, to make its own file at that path for the host to read. Best-effort while any "
        "read-only mount (a deny, a mask, a readable root) sits beneath a writable one: the host "
        "replacing the entry it is mounted on leaves the jail writing there"
    ),
)
FS_READ_CLAIM = Claim(
    name="fs_read",
    description="the command reads only the policy's roots, and nothing a mask names",
)
NETWORK_CLAIM = Claim(
    name="network",
    description=(
        "the command reaches no network: its own network namespace, with no interface. Never "
        "stronger than channel_exclusivity, since a host socket the jail can dial can carry the "
        "network for it"
    ),
)
ENV_CLAIM = Claim(
    name="env",
    description="the command's environment is exactly what the environment policy allows",
)


SOCKET_DIRECTORIES: tuple[str, ...] = ("/run", "/var/run", "/tmp", "/var/tmp", "/dev/shm")
"""Where a host keeps Unix sockets other processes listen on (the session bus, a container
runtime, an X server, a desktop's agents): a jail that can read one can dial what listens there,
since `connect` needs search on the path, not write (decision-0008 item 5). An embedder adds its
own runtime directory (`XDG_RUNTIME_DIR`) to these as host data."""


def _dialable(policy: FsPolicy, socket_directories: tuple[str, ...]) -> bool:
    """Whether a readable or writable root shows the jail any of `socket_directories`, or a path
    inside one, that no mask hides."""
    roots = (*policy.readable, *policy.writable)
    for place in socket_directories:
        for root in roots:
            seen = place if within(place, root) else root if within(root, place) else None
            if seen is not None and not any(within(seen, mask) for mask in policy.masks):
                return True
    return False


def _sees_host_paths(policy: FsPolicy) -> bool:
    """Whether the jail sees any host path a socket could sit in beyond its own channel
    directory: any readable or writable root, a file included (the host can rename a socket
    over it). brig's own mounts (its state directory's tmpfs, the supervisor script, the empty
    directory a mask shows) and the jail's own `/proc` and `/dev` are not the host's places. A
    mask cannot hide a whole root (`refusal`), so every root shows something of the host."""
    return bool(policy.readable or policy.writable)


def _beneath_writable(mounts: tuple[Mount, ...]) -> bool:
    """Whether any mount that is not writable (a read-only bind: a deny, a mask, a nested
    readable root; brig's tmpfs) sits where the jail would otherwise see a writable mount: the
    last mount strictly above its target is writable. The host replacing the entry it is mounted
    on (an editor saving by rename, a package manager swapping a directory) leaves the jail
    writing there. A pin is writable over writable, so it does not count."""
    for index, mount in enumerate(mounts):
        if mount.kind in (MountKind.WRITABLE, MountKind.REMOUNT_READ_ONLY):
            continue
        above = [
            earlier
            for earlier in mounts[:index]
            if earlier.kind is not MountKind.REMOUNT_READ_ONLY
            and earlier.target != mount.target
            and within(mount.target, earlier.target)
        ]
        if above and above[-1].kind is MountKind.WRITABLE:
            return True
    return False


def ceilings(
    policy: FsPolicy,
    mounts: tuple[Mount, ...],
    channels: Reservations | None,
    socket_directories: tuple[str, ...] = SOCKET_DIRECTORIES,
) -> frozendict[Claim, Grade]:
    """The strongest grade each claim can have for a jail compiled to `mounts` (decision-0008):
    what this compile states, before any jail runs. An e2e battery holds every one of these to
    what it measures (`at_most`), so none is stated stronger than the batteries show.

    `ENFORCED` needs a kernel mechanism that holds the claim, never a list of places that found
    nothing (decision-0008, the 2026-11-03 note). So:

    - `fs_write` is `BEST_EFFORT` while any mount that is not writable sits beneath a writable
      one (`_beneath_writable`: a deny, a mask, a readable root nested in a writable root),
      read from the compiled `mounts`, not the policy's roles. What it does cover beside that:
      the command cannot rename a directory strictly between a writable root and a deny, a mask
      or a readable root nested in it, since each that is there when the jail starts is pinned, a
      mount point of its own (`EBUSY`; a rename across one fails with `EXDEV`). What it does not:
      the host itself replacing, creating or removing an entry on the way while the jail runs.
    - `fs_read` is `BEST_EFFORT` while any mask is mounted: the host replacing a masked entry
      can detach the mask in the jail, wherever it is (measured on one kernel, not another).
    - `channel_exclusivity` is `VIOLATED` when a writable path the jail shares with the host is
      not a declared channel (a writable root included), or when the jail can see one of
      `socket_directories`; else `BEST_EFFORT` while it sees any host path at all
      (`_sees_host_paths`), since a socket the host keeps there can be dialled through a
      read-only mount; `ENFORCED` only with no root, which `interpreter_refusal` never lets
      through today.
    - `network` is never stronger than `channel_exclusivity`: the jail's own network namespace
      has no interface, but a host socket it can dial can carry the network.
    """
    masks = any(
        mount.target in policy.masks for mount in mounts if mount.kind is MountKind.READ_ONLY
    )
    if not set(writable_shared_paths(mounts)) <= set(declared_channel_paths(channels)):
        exclusivity = Grade.VIOLATED
    elif _dialable(policy, socket_directories):
        exclusivity = Grade.VIOLATED
    elif _sees_host_paths(policy):
        exclusivity = Grade.BEST_EFFORT
    else:
        exclusivity = Grade.ENFORCED
    return frozendict(
        {
            FS_WRITE_CLAIM: Grade.BEST_EFFORT if _beneath_writable(mounts) else Grade.ENFORCED,
            FS_READ_CLAIM: Grade.BEST_EFFORT if masks else Grade.ENFORCED,
            NETWORK_CLAIM: Grade.ENFORCED if at_most(Grade.ENFORCED, exclusivity) else exclusivity,
            ENV_CLAIM: Grade.ENFORCED,
            CHANNEL_EXCLUSIVITY_CLAIM: exclusivity,
        }
    )


def _governing(mounts: tuple[Mount, ...], path: str) -> Mount | None:
    """The last mount at or above `path`: what the jail sees there once every mount applied."""
    covering = [
        mount
        for mount in mounts
        if mount.kind is not MountKind.REMOUNT_READ_ONLY and within(path, mount.target)
    ]
    return covering[-1] if covering else None


def writable_shared_paths(mounts: tuple[Mount, ...]) -> tuple[str, ...]:
    """The host paths a jail with `mounts` can write: each writable bind still in effect at its
    own target once later mounts applied, as its source. Distinct, in mount order."""
    shared = [
        mount.source
        for mount in mounts
        if mount.kind is MountKind.WRITABLE and _governing(mounts, mount.target) == mount
    ]
    return tuple(dict.fromkeys(shared))


def declared_channel_paths(channels: Reservations | None) -> tuple[str, ...]:
    """The host paths of the channels a jail declared: its channel directory, or nothing.
    What `writable_shared_paths` is allowed to name under `CHANNEL_EXCLUSIVITY_CLAIM`."""
    if channels is None or not channels.reservations:
        return ()
    return (channels.directory.host_path,)


def compile_supervisor_launch(
    supervisor_path: tuple[str, ...], mounts: tuple[Mount, ...], cwd: str | None = None
) -> tuple[str, ...]:
    """The argv that starts `supervisor_path` as the jail's one process, behind `mounts`
    (`compile_mounts`), the virtual filesystems and the namespace flags, in `cwd` when one is
    given (bwrap's `--chdir`; the command inherits it from the supervisor, TASK-0028)."""
    chdir = ("--chdir", cwd) if cwd is not None else ()
    return (
        "bwrap",
        *render(mounts),
        *_VIRTUAL_FS_FLAGS,
        *chdir,
        *_NAMESPACE_FLAGS,
        *supervisor_path,
    )
