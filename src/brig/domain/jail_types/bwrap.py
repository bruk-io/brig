"""The bwrap jail type's compile: pure, from a request to the argv that starts the jail's
supervisor (decision-0001 rule 3; decision-0002).

`compile_mounts` turns the embedder's `FsPolicy` (intent: readable and writable roots, write
denies, masks; decision-0007) into an ordered tuple of `Mount`s, and everything else about the
jail's filesystem is read from that one tuple: `render` makes bwrap's flags from it, and
`writable_shared_paths` grades `CHANNEL_EXCLUSIVITY_CLAIM` from it. No second reader rebuilds
the order by hand.

The order is the policy's meaning. Entries mount shallowest path first, so the more specific
one wins where two overlap (bwrap applies mounts in argv order; a later mount replaces the
view beneath it). Then brig's own: an empty tmpfs over its state directory, with this jail's
supervisor script and channel directory bound back inside it, the tmpfs remounted read-only
(TASK-0019: the directory holds every jail's scripts and channels, and a Unix socket accepts a
connect through a read-only mount); then the virtual filesystems and the namespace flags.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from brig.domain.channels import Reservations
from brig.domain.claims import Claim
from brig.domain.plan import Plan
from brig.domain.policy.paths import FsPolicy, PathKind, within

_VIRTUAL_FS_FLAGS: tuple[str, ...] = ("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/sys")
"""Virtual-filesystem hygiene (TASK-0015, decision-0004), not a namespace/behavior
flag -- kept as its own constant rather than folded into `_NAMESPACE_FLAGS` below
for exactly that reason. `WHOLE_HOST_READ_ONLY`'s recursive `--ro-bind / /` carries
along whatever the host already has mounted at `/proc` and `/sys`, so without this,
a jailed command sees the *ambient host's* `/proc` (every real host pid, not only
its own namespace's) and the host's real `/sys` (block/bus/class/dev/devices/
firmware/kernel/module entries) -- measured directly against real bwrap
(decision-0004).

`--proc /proc` gives the jail a fresh procfs scoped to its own PID namespace,
structurally (not a mitigation riding on a host's own `ptrace_scope`): measured,
the jail's own `/proc` listing then contains only its own namespace's processes.
`--dev /dev` gives a minimal, functional device set (null, zero, random, urandom
and similar) instead of the host's real `/dev`, confirmed not to break the jail's
own basic command. `--tmpfs /sys` masks `/sys` empty rather than giving it a
namespace-scoped equivalent -- unlike procfs, sysfs has no per-namespace scoping
to offer instead, so absent is the only safe default; an embedder whose own policy
genuinely needs hardware introspection adds their own `/sys` bind back explicitly.

Unconditional, placed after the state directory's mask and before `_NAMESPACE_FLAGS`,
the same way that mask already is: never part of the caller's own
`FsPolicy`, since an embedder narrowing or widening their own policy has no
business accidentally re-exposing or hiding these.
"""

_NAMESPACE_FLAGS: tuple[str, ...] = (
    "--unshare-all",
    "--die-with-parent",
    "--new-session",
    "--cap-drop",
    "ALL",
    "--as-pid-1",
    "--",
)
"""bwrap's own namespace-isolation flags, after whatever `compile_mounts` names for
a policy's binds and ahead of whatever this jail type's driver names as the jail's
one process -- the supervisor (decision-0002), by way of `compile_supervisor_launch`.

``--cap-drop ALL`` (decision-0006): bwrap run by root drops no capability by default, so a
jail's command held nearly every capability in its namespaces, ``CAP_SYS_PTRACE`` among them,
which overrides the supervisor's non-dumpable flag and lets the command reach PID 1. With it
the jail holds none, whoever runs brig.

A policy's binds have to come first: without at least one bind, bwrap pivots into an
empty new root and `execvp` finds nothing there to run, regardless of exit code --
`WHOLE_HOST_READ_ONLY`'s whole-host read-only bind is the thinnest policy that lets
the supervisor's own file be reachable inside the jail at all (presentation's own
wiring documents exactly how it relies on that). ``--unshare-all`` isolates every
namespace bwrap can; ``--die-with-parent`` ties the jail's lifetime to the process
that started it.

``--as-pid-1`` (TASK-0001.15 step 4, measured against real bwrap in a privileged
Docker container -- bwrap itself refuses ``--unshare-all`` outside one, a container
limitation, not a finding about this flag) is load-bearing for decision-0002's own
premise, not an optional hardening: ``--unshare-all`` implies ``--unshare-pid``, and
bwrap's *default* behaviour there installs its own reaper process as the namespace's
real PID 1, with whatever this argv names after ``--`` running as PID 2 instead --
measured directly (the supervisor's own ``started`` event named a pid of 3, not 1,
without this flag; 1, with it). Without it, an orphan reparented inside the
namespace reparents to bwrap's own reaper, never to the supervisor, and
``program.py``'s own "reaps everything reparented to it, including orphans"
(its own module docstring) silently stops being true for anything bwrap's reaper
catches instead. ``--as-pid-1`` makes the supervisor itself the one process bwrap
execs into that role, with no separate reaper in between.

``--new-session`` (TASK-0001.05 AC#2) closes the TIOCSTI escape bwrap's own
documentation warns about: a process sharing a controlling terminal with something
outside the jail can, without its session detached from that terminal, inject
keystrokes back onto it via the TIOCSTI ioctl and escape through whatever reads them
next. Stated here, as this jail type's own policy, rather than left to infra's spawn:
on the toolchain this project's own CI runs, this flag is the *only* thing closing that
hole, and it is load-bearing rather than defense in depth.

That is a correction of what TASK-0001.05's review measured on one host. The review
found infra's ``os.posix_spawnp(..., setsid=True)`` (TASK-0001.06's safe-spawn work)
running unconditionally, before bwrap's own argv is ever parsed, and concluded this
flag could never be credited for the closure. Measured since, on real Linux
(TASK-0001.12): ``setsid=True`` is not available on every interpreter -- it is compiled
out of uv's managed CPython, the build this project's ``pyproject.toml`` and CI select
-- so ``brig.infra.processes.spawn`` falls back to a new process group alone there,
which leaves the controlling terminal shared and the hole open. Infra reports which it
got as ``SpawnedProcess.session_detached``. Where that is ``False``, nothing but
``--new-session`` closes this, and the flag's contribution is attributable after all;
where it is ``True``, infra's session already closed it first and the flag is the
redundant half, keeping the property true should that ever stop. Either way
``tests/e2e/test_tiocsti_battery.py`` grades the property end to end (TIOCSTI stays
denied) rather than which layer denies it; grading the attribution itself is still
tracked separately (TASK-0001.11).
"""

_INHERITABLE_FDS: tuple[int, ...] = (0, 1, 2)
"""The complete set of file descriptors bwrap's own jailed process may inherit across
the spawn (`Plan.inheritable_fds`'s own docstring: a complete allow-list, not an
addition to an implicit default).

Just stdin, stdout and stderr: bwrap's own argv above opens no fd of its own that needs
naming (no ``--info-fd``, no ``--sync-fd``; this jail type uses neither). Named here
unchanged since the walking skeleton, when this was the real command's own policy --
TASK-0001.15 step 4 made the jail's directly-spawned process the supervisor instead
(`Plan`'s own docstring), and `StartSupervisedCommand` carries no `inheritable_fds`
field to hand this to, so the value `compile_run` returns here currently reaches no
effect at all. Left stated rather than deleted, as the open question `domain/effects.py`
already records: whichever of the supervisor's own exec or a later effect field ends up
enforcing this is still open.
"""


def compile_run(command: tuple[str, ...], env: tuple[tuple[str, str], ...] = ()) -> Plan:
    """Compile a request to run `command`, in `env`, as the one command bwrap's
    supervisor runs as its own child (decision-0002).

    This jail type never refuses a request (see `domain/plan.py`), so the walking
    skeleton's compile always produces a `Plan`.
    """
    return Plan(argv=command, inheritable_fds=_INHERITABLE_FDS, env=env)


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

_RANK = {"readable": 0, "writable": 1, "deny": 2, "mask": 3}
"""At one path, which entry mounts last and so wins: a mask over a deny over a writable root
over a readable one."""


def _depth(path: str) -> int:
    return 0 if path == "/" else path.count("/")


def _kept(policy: FsPolicy, kinds: Mapping[str, PathKind]) -> list[tuple[str, str]]:
    """The policy's entries that need a mount, as `(role, path)`.

    A write deny or mask whose path is absent needs one only under a writable root, where the
    command could otherwise create it; elsewhere nothing in the jail can make it, and bwrap
    could not make its mountpoint on a read-only mount either. A deny or mask beneath a mask is
    hidden already. A write deny outside every writable root is read-only already.
    """
    entries = [("readable", p) for p in policy.readable]
    entries += [("writable", p) for p in policy.writable]
    for role, paths in (("deny", policy.write_denies), ("mask", policy.masks)):
        for path in paths:
            if any(other != path and within(path, other) for other in policy.masks):
                continue
            writable = any(within(path, root) for root in policy.writable)
            absent = kinds.get(path, PathKind.ABSENT) is PathKind.ABSENT
            if role == "deny" and not writable:
                continue
            if absent and not writable:
                continue
            entries.append((role, path))
    return sorted(set(entries), key=lambda entry: (_depth(entry[1]), _RANK[entry[0]], entry[1]))


def _mount_for(role: str, path: str, kind: PathKind, empty_dir: str) -> Mount:
    match role:
        case "readable" | "deny":
            source = empty_dir if kind is PathKind.ABSENT and role == "deny" else path
            return Mount(MountKind.READ_ONLY, path, source)
        case "writable":
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

    `kinds` is what is at each write deny's and mask's path on the host (presentation looks;
    a path it does not name reads as absent). `empty_dir` is an empty, read-only host
    directory brig owns: the source for a masked directory, and for a deny or mask at an
    absent path, so the command can neither read nor create anything there. `refusal` in
    `domain/policy/paths.py` must have passed first.
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
        "the only paths this jail can write that the host can also reach are the "
        "channels it declared: every writable bind compiled for it is the per-jail "
        "channel directory, and nothing else the host shares with it is writable "
        "(old SPEC law 9: nothing crosses the boundary anonymously)"
    ),
)
"""What the compile claims about the paths it mounts (old SPEC law 9). A claim, never a grade:
`domain/grades.py`'s `grade` decides that from evidence a battery measured."""


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
    supervisor_path: tuple[str, ...], mounts: tuple[Mount, ...]
) -> tuple[str, ...]:
    """The argv that starts `supervisor_path` as the jail's one process, behind `mounts`
    (`compile_mounts`), the virtual filesystems and the namespace flags."""
    return ("bwrap", *render(mounts), *_VIRTUAL_FS_FLAGS, *_NAMESPACE_FLAGS, *supervisor_path)
