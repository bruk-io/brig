"""bwrap's slice of the domain (decision-0001 rule 3): compiling a request, nothing else.

The matching driver, ``presentation/drivers/bwrap.py``, performs the effects
``domain/operations.py`` yields for whatever ``Plan`` this module compiles; no module here
imports that driver, or any other jail type's modules (rule 3).

TASK-0001.15 step 4: ``compile_run`` no longer wraps the real command in bwrap's own
flags -- the jail's one process is the supervisor now (decision-0002), and ``Plan.argv``
is the command `operations.create()` hands it to run as *its* child, over the wire, not
something this jail type spawns directly any more. ``compile_supervisor_launch`` is the
new home for bwrap's own wrapping job: presentation's driver calls it with wherever it
found the supervisor's own file, since locating that file is I/O domain does not do
(rule 2).

TASK-0001.16: ``compile_supervisor_launch`` now also takes an ``FsPolicy``
(`domain/policy/paths.py`) and translates its binds into bwrap's own
``--ro-bind``/``--bind`` flags, ahead of the namespace-isolation flags below --
replacing the single hardcoded ``--ro-bind / /`` placeholder this module used to
carry as ``_BWRAP_ARGV``. That placeholder is gone; ``WHOLE_HOST_READ_ONLY``
(`domain/policy/paths.py`) is the default ``FsPolicy`` every caller gets when it
names none of its own, reproducing the exact flags the old placeholder produced
(`tests/unit/test_bwrap_compile.py`'s byte-exact assertion on
``compile_supervisor_launch``'s output is the proof nothing currently passing
regressed). This landed on ``compile_supervisor_launch``, not ``compile_run``:
by TASK-0001.15 step 4, ``compile_run`` builds no bwrap argv at all any more (it
only names the real command the supervisor runs as its own child, see `Plan`'s own
docstring) -- a policy parameter there would reach no flag, the exact "no current
reader" gap `Plan.inheritable_fds`'s own docstring already records for a different
field. ``compile_supervisor_launch`` is what actually builds the supervisor's own
bwrap-wrapped launch line, so that is where a filesystem policy has to land to mean
anything.

TASK-0006: ``compile_supervisor_launch`` also takes ``state_dir`` -- the already-
resolved directory presentation found the assembled supervisor script written
into (`infra/state_dir.py`; locating and creating it is I/O, rule 2, so domain
only ever receives the plain string presentation hands in, the same pattern
``supervisor_path`` itself already follows). It adds one unconditional ``--ro-bind state_dir
state_dir`` (since TASK-0019, a mask in its place: see below), after ``policy``'s own binds and
before ``_NAMESPACE_FLAGS``: structural, like ``_NAMESPACE_FLAGS``/``_INHERITABLE_FDS`` below, never
part of the caller's own ``FsPolicy``, and bwrap applies overlapping binds in argv order (later
wins), so placing it after the policy's own binds means a policy bind at *exactly* this same path
can never shadow it first (``tests/e2e/test_fs_policy_battery.py``'s
``test_a_policy_bind_at_the_state_dirs_own_jail_path_does_not_shadow_it``, verified against real
bwrap).

That is a narrower guarantee than "reachable regardless of the caller's own
policy", which an earlier revision of this docstring claimed. Measured against
real bwrap (adversarial review of TASK-0006/0009, with ``BRIG_HOME`` pointed at
an otherwise-untouched ancestor so the result is not confounded by anything
else that ancestor happens to also hold): a *writable* ancestor bind of
``state_dir`` works regardless of whether its own source contains
``state_dir``'s leaf, and a *read-only* ancestor bind works when its source
does contain that leaf -- but a read-only ancestor bind whose source does
*not* contain it fails, because bwrap creates a bind's missing mountpoint
directories in the new root before applying that bind's own mount, in argv
order, and by the time this unconditional bind runs the ancestor already
occupies that subtree read-only. The caller's own ``FsPolicy`` cannot make
this bind *vanish*, or make a same-path bind *win* over it -- both still
hold.

TASK-0001.22: two candidate fixes that would make the shape above work
regardless were measured against real bwrap and killed. ``--dir <state_dir>``
issued ahead of the ancestor bind EROFSes identically (the ancestor bind's own
mountpoint-creation step is what fails, before ``--dir`` is even reached, in
both orderings tried); issued after the ancestor bind, it hits the same EROFS
``--dir`` was meant to avoid. Giving the state dir a fixed, always-topmost
jail path (e.g. ``/brig-state``, parallel to ``/``) does not help either, and
is strictly worse: measured directly, it breaks the *default* policy itself
(``WHOLE_HOST_READ_ONLY``), because that path does not exist on the real host
root either, and creating it hits the exact same read-only-mountpoint EROFS
one mount earlier than this bug ever reached. So this module does not attempt
to make the shape reachable; ``covering_ancestor_bind`` (below) is the pure
half of refusing it instead -- `presentation/api.py`'s own
``_check_state_dir_reachable`` is the shell that uses it, with the one host
filesystem check (whether the governing ancestor's own source already
contains ``state_dir``'s leaf) this module's own purity rule (rule 2) keeps
out of here, and raises ``StateDirectoryUnreachable`` before bwrap is ever
invoked, rather than letting this surface as ``JailExitUnknown`` ->
``JailTeardownFailed``.

TASK-0019: the state directory is no longer bound whole. It holds every jail's
supervisor script and channel directory, and a Unix socket accepts a connect through a
read-only mount (measured: one jail dialled another's reserved channel through that
bind). In its place: ``--tmpfs state_dir``, a read-only bind of this jail's own
supervisor script, the channel directory's bind when channels are declared, then
``--remount-ro state_dir`` (``_compile_state_dir_mask``, ``_compile_state_dir_seal``).
A tmpfs needs its mountpoint exactly as the bind did, so everything measured above about
which ancestor binds reach it holds unchanged, and the shadowing guarantee with it.

TASK-0001.28: this module also *states* the `channel_exclusivity` claim (old SPEC law 9:
nothing crosses the boundary anonymously) as `CHANNEL_EXCLUSIVITY_CLAIM` below, together with
the two pure functions that say what the claim is about --
`writable_shared_paths`, the enumeration AC#2 asks for, and
`declared_channel_paths`, what that enumeration is compared against. Nothing here grades
anything (decision-0001 rule 11): `domain/grades.py`'s `grade` is the one producer of a
report, fed by `Evidence` an e2e battery measured. The claim lives here rather than in a
battery because AC#1 says bwrap's compile is what states it -- the same place
`compile_supervisor_launch` already states every other property of the jail it builds --
and because `domain/claims.py`'s own docstring asks a jail type's compile to be the
source of its own claims.
"""

from brig.domain.channels import Reservations
from brig.domain.claims import Claim
from brig.domain.plan import Plan
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, Bind, FsPolicy

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
    "--as-pid-1",
    "--",
)
"""bwrap's own namespace-isolation flags, after whatever `_compile_binds` names for
a policy's binds and ahead of whatever this jail type's driver names as the jail's
one process -- the supervisor (decision-0002), by way of `compile_supervisor_launch`.

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


def _compile_binds(policy: FsPolicy) -> tuple[str, ...]:
    """Translate `policy`'s own binds into bwrap's `--ro-bind`/`--bind` flags: one
    bind, one `(flag, host_path, jail_path)` triple, in the order `policy.binds`
    names them -- `--bind` for a writable `Bind`, `--ro-bind` otherwise, each
    followed by its `host_path` then its `jail_path` (bwrap's own argument order
    for both flags).
    """
    return tuple(
        flag
        for bind in policy.binds
        for flag in ("--bind" if bind.writable else "--ro-bind", bind.host_path, bind.jail_path)
    )


def covering_ancestor_bind(policy: FsPolicy, state_dir: str) -> Bind | None:
    """Which of `policy`'s own binds, if any, governs `state_dir`'s own parent
    directory at the moment `compile_supervisor_launch`'s unconditional bind
    actually runs (TASK-0001.22): the last bind in `policy.binds` whose own
    `jail_path` is a strict ancestor of `state_dir` -- bwrap mounts in argv
    order, and a later mount at a path replaces the whole view beneath it
    (the same "later wins" semantics `compile_supervisor_launch`'s own
    docstring already states for an *exact*-path overlap), so whichever such
    bind comes last in `policy.binds` is the one still in effect at
    `state_dir`'s parent once every one of `policy`'s own binds has applied,
    just before the unconditional bind itself does. `None` when no bind in
    `policy` names an ancestor of `state_dir` at all -- bwrap's own new root
    starts as a writable tmpfs, so an uncovered ancestor needs no mount of
    its own to let a missing `state_dir` be created in it, measured directly
    against real bwrap.

    Pure (rule 2): a path-string computation over `policy` and `state_dir`,
    touching no filesystem. Deciding whether the returned bind actually
    *blocks* `state_dir`'s own creation needs to know whether that bind's own
    source already contains `state_dir`'s leaf, which is I/O (`os.path`/
    `pathlib`) -- left to `presentation/api.py`'s own
    `_check_state_dir_reachable`, the one layer allowed to do it.

    Compares `jail_path`/`state_dir` as literal strings, not normalized paths
    -- a `policy` naming an un-normalized ancestor (e.g. `/root/../root`) is
    outside what this function reasons about, the same way `FsPolicy`/`Bind`
    (`domain/policy/paths.py`) make no normalization promise of their own.

    Picking the *last* ancestor bind, specifically (not the longest-matching
    one, or the one with the fewest path components), is what matches real
    bwrap when two of `policy`'s own binds are both ancestors of `state_dir`
    at different depths: measured directly, a later, *shallower* read-only
    bind hides an earlier, deeper one entirely (the view it replaces includes
    everything nested under it), so the shallower one -- last in argv order --
    is correctly what this returns and what `_check_state_dir_reachable` then
    judges. The reverse arrangement (an earlier shallow read-only bind, then a
    later deep bind nested inside it) is a different, pre-existing failure
    this function does not need to detect: that later bind's own mountpoint
    creation already fails against bwrap, for reasons having nothing to do
    with `state_dir` -- measured directly, the identical jail breaks the same
    way with no `state_dir` bind appended at all, so a caller policy shaped
    like that was already unmountable before this function or
    `compile_supervisor_launch`'s own unconditional bind ever entered the
    picture.
    """
    ancestor_binds = tuple(
        bind
        for bind in policy.binds
        if bind.jail_path != state_dir and state_dir.startswith(bind.jail_path.rstrip("/") + "/")
    )
    return ancestor_binds[-1] if ancestor_binds else None


CHANNEL_EXCLUSIVITY_CLAIM = Claim(
    name="channel_exclusivity",
    description=(
        "the only paths this jail can write that the host can also reach are the "
        "channels it declared: every writable bind compiled for it is the per-jail "
        "channel directory, and nothing else the host shares with it is writable "
        "(old SPEC law 9: nothing crosses the boundary anonymously)"
    ),
)
"""What `compile_supervisor_launch` claims about the paths it compiles (TASK-0001.28
AC#1, decision-0002 items 3 and 4; old SPEC law 9).

Stated here, by the module that actually compiles the jail's own argv, rather than
invented by a battery -- `domain/claims.py`'s own docstring asks for exactly that, and
`tests/e2e/test_claims_wiring.py`'s own `FD_INHERITANCE_CLAIM`/`TIOCSTI_CLOSURE_CLAIM`
are the weaker pattern (a battery naming a claim in for the first time) that
decision-0002 item 4 tolerates but AC#1 does not ask for. Public (exported from
`brig/__init__.py`) because an embedder reading a report needs the same `Claim` value
the compile states, not a second one that merely looks like it.

A claim, never a grade: this says what the jail's own compiled argv asserts, and
nothing about whether it holds -- `domain/grades.py`'s `grade` decides that from
`Evidence` an e2e battery measured against a real jail.
"""


def writable_shared_paths(
    policy: FsPolicy, state_dir: str, channels: Reservations | None
) -> tuple[str, ...]:
    """Every path a jail compiled from `policy`/`state_dir`/`channels` can write that
    the host can also reach (TASK-0001.28 AC#2): the enumeration
    `CHANNEL_EXCLUSIVITY_CLAIM` above is graded from.

    **Not** a filter over `policy.binds` on `Bind.writable` -- that predicate is wrong,
    and measured so. `compile_supervisor_launch` emits its own mounts *outside*
    `policy.binds` entirely (the unconditional read-only mask over `state_dir`, and the
    writable channel-directory bind nested inside it, in that order), and bwrap applies
    overlapping binds in argv order, later wins -- so what governs any given location is
    the *last* bind in the compiled sequence whose own `jail_path` equals that location
    or is a strict ancestor of it, exactly the "later wins, nested or exact, argv order"
    reasoning `covering_ancestor_bind` above already encodes for the strict-ancestor
    case. A bare `.writable` filter would miss the channel bind (never in
    `policy.binds`) and would wrongly report a writable policy bind that a later
    read-only ancestor shadowed.

    The compiled sequence is reconstructed from `policy`/`state_dir`/`channels` here,
    in the same order `compile_supervisor_launch` builds it, rather than by calling that
    function and parsing its own rendered `--bind`/`--ro-bind` argv back apart: parsing
    flags out would couple this to exact flag text and break the moment
    `_VIRTUAL_FS_FLAGS` or anything else shifts position in that argv. The ordering fact
    is stated once, in `compile_supervisor_launch`'s own body; this function and
    `_check_channel_directory_reachable` (`presentation/api.py`) are the two readers that
    depend on it, and either reordering there silently invalidates both.

    Candidates are identified in *jail-path* space (which is what "which bind governs
    this location" is about), but each one that comes out writable is returned as its
    *host-side* location under whatever bind governs it: `g.host_path` for the suffix
    the candidate has past `g.jail_path` -- the same "host equivalent" formula
    `presentation/api.py`'s `_check_state_dir_reachable` already computes for a nested
    path. For every shape this codebase produces today (`ChannelDirectory`'s own
    docstring: `host_path == jail_path` for bwrap binds, and every `Bind` an embedder
    writes binds a path at its own name) the suffix is empty and the two spaces
    coincide; the formula is written in general rather than assumed, the same discipline
    `covering_ancestor_bind`'s own docstring states for itself. Only a candidate whose
    governing bind is writable is translated -- an excluded candidate's host-side
    location is never needed. Distinct paths only, in compiled order.

    Pure (rule 2): a path-string computation over plain data, touching no filesystem.
    """
    candidates = (
        *policy.binds,
        # The mask over `state_dir` (TASK-0019): a tmpfs, so nothing the host shares and
        # never writable once sealed. A non-writable entry governs exactly as it does, and
        # the supervisor script bound back inside it is read-only too, so neither counts.
        Bind(host_path=state_dir, jail_path=state_dir),
        *(
            (
                Bind(
                    host_path=channels.directory.host_path,
                    jail_path=channels.directory.jail_path,
                    writable=True,
                ),
            )
            if channels is not None and channels.reservations
            else ()
        ),
    )
    shared: list[str] = []
    for candidate in candidates:
        governing = _governing_bind(candidates, candidate.jail_path)
        if governing is None or not governing.writable:
            continue
        suffix = candidate.jail_path[len(governing.jail_path.rstrip("/")) :]
        host_equivalent = governing.host_path.rstrip("/") + suffix
        if host_equivalent not in shared:
            shared.append(host_equivalent)
    return tuple(shared)


def _governing_bind(binds: tuple[Bind, ...], jail_path: str) -> Bind | None:
    """The last of `binds`, in argv order, whose own `jail_path` is `jail_path` itself
    or a strict ancestor of it -- which is what actually governs that location inside
    the jail once bwrap has applied every bind, since a later mount at a path replaces
    the whole view beneath it.

    `covering_ancestor_bind` above generalised to include the exact-match case rather
    than the strict-ancestor one alone: that function answers "what governs this
    path's *parent*", because the bind it was written for (`state_dir`'s own
    unconditional bind) is always mounted last and so never has to be found in the
    sequence at all. Here the path being asked about is a bind's own `jail_path`, so
    that bind is itself the last match unless something later covers it.

    `None` only for an empty `binds`, which cannot happen for the sequence
    `writable_shared_paths` builds -- it always contains at least the unconditional
    `state_dir` bind -- but is stated rather than assumed.

    Compares `jail_path`/`bind.jail_path` as literal strings, not normalized paths, the
    same way `covering_ancestor_bind` and `FsPolicy`/`Bind` themselves do.
    """
    matches = tuple(
        bind
        for bind in binds
        if bind.jail_path == jail_path or jail_path.startswith(bind.jail_path.rstrip("/") + "/")
    )
    return matches[-1] if matches else None


def declared_channel_paths(channels: Reservations | None) -> tuple[str, ...]:
    """The host paths of the channels a jail declared (TASK-0001.28 AC#2): what
    `CHANNEL_EXCLUSIVITY_CLAIM` says the jail's writable, host-shared paths are allowed
    to be, so a caller can compare it against `writable_shared_paths` and see the
    difference.

    The channel *directory* is what `_compile_channel_bind` above actually binds
    writable -- one bind for the directory, never one per reservation inside it -- so
    that is what this names, not each reservation's own file. Host-path space, matching
    what `writable_shared_paths` returns, so the two compare directly with no second
    translation anywhere.

    `()` for `channels is None` or a set declaring nothing: `_compile_channel_bind`
    binds nothing in either case, so the jail claims no writable path of its own.
    """
    if channels is None or not channels.reservations:
        return ()
    return (channels.directory.host_path,)


def _compile_channel_bind(channels: Reservations | None) -> tuple[str, ...]:
    """The writable bind of the per-jail channel directory (TASK-0001.25), or nothing
    when `channels` declares no channel at all.

    Writable because the jailed command creates its sockets there. Bound host path to
    jail path (`ChannelDirectory`'s own docstring: equal for bwrap today).
    """
    if channels is None or not channels.reservations:
        return ()
    directory = channels.directory
    return ("--bind", directory.host_path, directory.jail_path)


def _compile_state_dir_mask(state_dir: str, supervisor_script: str) -> tuple[str, ...]:
    """Mask brig's state directory with an empty tmpfs and bind back only this jail's
    own supervisor script, read-only (TASK-0019) -- the opening half of the mask;
    `_compile_state_dir_seal` is the closing half, after the channel directory's bind.

    The state directory holds every jail's supervisor script and channel directory, and a
    Unix socket accepts a connect through a read-only mount, so what of it a jail sees it
    can dial (measured at a7e7f45: one jail dialled another's reserved channel through the
    `--ro-bind <state_dir> <state_dir>` this replaced). The tmpfs comes after `policy`'s
    own binds, so it also covers a policy that binds an ancestor of the state directory
    (`WHOLE_HOST_READ_ONLY`'s `/`): later wins, as for every bind here. It needs its
    mountpoint exactly as that bind did, so `covering_ancestor_bind`'s refusal still
    applies unchanged.
    """
    return ("--tmpfs", state_dir, "--ro-bind", supervisor_script, supervisor_script)


def _compile_state_dir_seal(state_dir: str) -> tuple[str, ...]:
    """Remount the state directory's tmpfs read-only once everything inside it is bound
    (TASK-0019), so the jail cannot write there either -- the same read-only view the
    whole-directory bind gave before.

    bwrap's `--remount-ro` is not recursive (measured against bubblewrap 0.9.0): the
    channel directory's own writable bind inside the tmpfs stays writable. It has to come
    after that bind, since the bind's mountpoint is created in the tmpfs while it is still
    writable.
    """
    return ("--remount-ro", state_dir)


def compile_supervisor_launch(
    supervisor_path: tuple[str, ...],
    *,
    state_dir: str,
    supervisor_script: str,
    policy: FsPolicy = WHOLE_HOST_READ_ONLY,
    channels: Reservations | None = None,
) -> tuple[str, ...]:
    """Wrap `supervisor_path` in this jail type's own bwrap flags, so bwrap starts
    the supervisor named there as the jail's one process, seeing exactly the paths
    `policy` names, plus, of `state_dir`, its own `supervisor_script` and channel
    directory, and nothing else (TASK-0001.16, TASK-0006, TASK-0019) --
    this function's own job before TASK-0001.15 step 4 pointed it at the real
    command directly, now aimed at the supervisor instead (decision-0002).

    `policy` defaults to `WHOLE_HOST_READ_ONLY` (`domain/policy/paths.py`): the
    whole host root, read-only -- the thinnest policy that lets the supervisor's
    own file be reachable inside the jail at all, reproducing exactly the flags
    the single hardcoded `--ro-bind / /` bind this function carried before this
    parameter existed, so a caller that never names a policy of its own sees no
    change.

    `state_dir` has no default: every caller passes the state directory it
    actually resolved (`infra/state_dir.py`) and wrote the supervisor's own script
    into, masked unconditionally in the compiled argv (`_compile_state_dir_mask`) --
    always present, always after `policy`'s own binds, so a same-path policy bind can
    never shadow it, and an ancestor bind (`WHOLE_HOST_READ_ONLY`'s `/`) does not
    expose the other jails' scripts and channels beneath it
    (this module's own docstring has the measured limits of that guarantee: it
    does not make every ancestor bind a policy might name safe -- a `policy`
    naming a *read-only* ancestor bind of `state_dir` whose own source lacks
    `state_dir`'s leaf is instead refused before this function is ever called,
    `presentation/api.py`'s `_check_state_dir_reachable` using this module's own
    `covering_ancestor_bind`, TASK-0001.22) -- a plain string, the same way
    `supervisor_path` already crosses from presentation into domain (rule 2:
    domain does no I/O to locate either).

    `supervisor_script` is the file `supervisor_path` runs, inside `state_dir`: the one
    file of that directory the mask binds back, read-only (TASK-0019). Named on its own
    rather than read off `supervisor_path`'s last element, so the compile does not
    depend on how that argv is spelled.

    `supervisor_path` is presentation's own concern: this jail type's driver finds
    wherever the file `infra/supervisor/wire.py` and `program.py` assemble into
    actually lives (`domain/jail_types/bwrap.py`'s module docstring) and hands the
    already-resolved argv in here as plain strings -- domain states the policy
    (which paths, namespace isolation, `--new-session`'s TIOCSTI closure) but does
    no I/O of its own to locate anything (rule 2).

    `channels` (TASK-0001.25), when it declares at least one channel, adds one
    writable `--bind` of its per-jail channel directory, between the state
    directory's mask and its seal: the channel directory lives beneath brig's state
    directory, bwrap applies binds in argv order (later wins), so it has to come after
    the tmpfs to show through it, and before `--remount-ro`, which needs the bind's
    mountpoint already made in the tmpfs. Declaring none adds nothing there. The host
    directory must exist before bwrap runs, as the bind's source; creating it is
    `infra/sockets.py`'s (TASK-0001.26), not this function's.
    """
    return (
        "bwrap",
        *_compile_binds(policy),
        *_compile_state_dir_mask(state_dir, supervisor_script),
        *_compile_channel_bind(channels),
        *_compile_state_dir_seal(state_dir),
        *_VIRTUAL_FS_FLAGS,
        *_NAMESPACE_FLAGS,
        *supervisor_path,
    )
