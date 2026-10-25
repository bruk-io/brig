"""Unit test for the `channel_exclusivity` claim's enumeration (TASK-0001.28 AC#2).

Pure, no I/O: `writable_shared_paths` and `declared_channel_paths` take plain
`FsPolicy`/`Reservations` data and hand back plain tuples, so every case here is a
literal in and a literal out -- no real jail, no real filesystem, no `tmp_path`.

The case that matters most is
`test_a_writable_bind_shadowed_by_a_later_read_only_ancestor_is_excluded` below. The
tempting implementation of `writable_shared_paths` is
`[b.jail_path for b in policy.binds if b.writable]`, and it passes most of this file
by coincidence -- the channel-directory bind genuinely is `writable=True`, and the
default policy genuinely names nothing writable -- while never reasoning about argv
order at all. Real bwrap applies overlapping binds in argv order, later wins, and
`compile_supervisor_launch` relies on exactly that to keep the channel bind writable
inside the read-only `state_dir` bind (TASK-0001.26/.27's own CI measured it). A bare
filter would report a writable bind that a later read-only ancestor had already
replaced, which is a path the jail cannot in fact write -- the one case here that
tells the two implementations apart.
"""

from brig.domain.channels import ChannelDirectory, Reservation, Reservations
from brig.domain.grades import Grade, grade
from brig.domain.jail_types.bwrap import (
    CHANNEL_EXCLUSIVITY_CLAIM,
    declared_channel_paths,
    writable_shared_paths,
)
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, Bind, FsPolicy

_STATE_DIR = "/state/brig"
"""A plain string stand-in for brig's resolved state directory, the same shape
`tests/unit/test_bwrap_compile.py`'s own `_STATE_DIR_PLACEHOLDER` uses: domain treats
it as an opaque string (rule 2 -- it does no I/O to resolve one), so any string proves
what a real resolved path would.
"""

_CHANNEL_DIR = _STATE_DIR + "/channels/abc"
"""A channel directory beneath the state directory, where `presentation/api.py`'s own
default allocator (`_allocate_channel_directory`) places one.
"""


def _channels(host_path: str = _CHANNEL_DIR, jail_path: str | None = None) -> Reservations:
    """One declared channel in a channel directory `host_path` wide, bound at
    `jail_path` (its own host path by default -- `ChannelDirectory`'s own stated
    invariant for bwrap today).
    """
    where = host_path if jail_path is None else jail_path
    return Reservations(
        directory=ChannelDirectory(host_path=host_path, jail_path=where),
        reservations=(
            Reservation(name="ctl", bound_path=host_path + "/ctl", endpoint=where + "/ctl"),
        ),
    )


def test_no_channels_under_the_default_policy_shares_nothing_writable() -> None:
    """Neither bind the default policy has is writable on its own path: the whole
    host root is read-only, and the unconditional `state_dir` bind
    `compile_supervisor_launch` appends is read-only too. So a jail declaring no
    channel shares nothing writable with the host, even though the sequence it was
    compiled from has two binds in it -- the state-dir bind is a *candidate* (always
    present, unconditional) that has to be proven not to come out writable on its own
    exact path, which is what this case is for.
    """
    assert writable_shared_paths(WHOLE_HOST_READ_ONLY, _STATE_DIR, None) == ()


def test_declared_channels_share_exactly_the_channel_directory() -> None:
    """One declared channel binds the channel directory writable, nested inside the
    read-only `state_dir` bind that `compile_supervisor_launch` mounts *first*
    (bwrap's later bind wins, which is what keeps the channel directory writable at
    all) -- so exactly that directory's path comes back. A bare `.writable` filter
    over `policy.binds` would also pass this case, by accident: the channel bind is
    genuinely writable, and it is not in `policy.binds` at all. The shadowed-bind case
    below is the one that discriminates.
    """
    channels = _channels()

    assert writable_shared_paths(WHOLE_HOST_READ_ONLY, _STATE_DIR, channels) == (_CHANNEL_DIR,)
    assert declared_channel_paths(channels) == (_CHANNEL_DIR,)
    # The state directory's own path is not in the result, regardless: a channel
    # directory nested inside it being writable is not the same as the state
    # directory itself being writable (AC#2 names the state-dir bind explicitly).
    assert _STATE_DIR not in writable_shared_paths(WHOLE_HOST_READ_ONLY, _STATE_DIR, channels)


def test_a_policys_own_writable_bind_is_reported_alongside_the_channel_directory() -> None:
    """A policy that names a writable bind of its own -- unlike `WHOLE_HOST_READ_ONLY`
    -- adds a second shared writable path on top of the declared channel's, so the
    enumeration is not merely "the channel directory or nothing".
    """
    policy = FsPolicy(
        binds=(
            *WHOLE_HOST_READ_ONLY.binds,
            Bind(host_path="/scratch", jail_path="/scratch", writable=True),
        )
    )

    assert writable_shared_paths(policy, _STATE_DIR, _channels()) == (
        "/scratch",
        _CHANNEL_DIR,
    )


def test_a_writable_bind_shadowed_by_a_later_read_only_ancestor_is_excluded() -> None:
    """The discriminating case (see this module's own docstring): a writable policy
    bind at `/data/nested`, followed in argv order by a read-only bind at `/data` that
    replaces the whole view beneath it. Real bwrap applies the later mount last, so
    nothing under `/data` is writable any more -- `/data/nested` included -- and this
    enumeration has to say so.

    A bare `[b.jail_path for b in policy.binds if b.writable]` filter reports
    `/data/nested` here, which is a path the compiled jail cannot write. Reversing the
    two binds is the control that keeps this case from being satisfied by an
    implementation that simply always excludes nested binds: with the read-only
    ancestor *first* and the writable bind later, the writable one genuinely does win
    and must be reported.
    """
    shadowed = FsPolicy(
        binds=(
            *WHOLE_HOST_READ_ONLY.binds,
            Bind(host_path="/host-nested", jail_path="/data/nested", writable=True),
            Bind(host_path="/host-data", jail_path="/data"),
        )
    )
    winning = FsPolicy(
        binds=(
            *WHOLE_HOST_READ_ONLY.binds,
            Bind(host_path="/host-data", jail_path="/data"),
            Bind(host_path="/host-nested", jail_path="/data/nested", writable=True),
        )
    )

    assert writable_shared_paths(shadowed, _STATE_DIR, None) == ()
    assert writable_shared_paths(winning, _STATE_DIR, None) == ("/host-nested",)


def test_the_state_directories_own_path_is_never_reported_even_when_a_policy_names_one() -> None:
    """AC#2 names the state-dir bind explicitly, and this is why: it is the one bind
    `compile_supervisor_launch` always adds, so it is always a candidate. A policy
    naming a *writable* bind at exactly the state directory's own jail path is
    shadowed by that unconditional bind, which `compile_supervisor_launch` mounts
    later -- so the state directory stays read-only and its path must not appear, even
    though the policy asked for it writable (`tests/e2e/test_fs_policy_battery.py`'s
    own `test_a_policy_bind_at_the_state_dirs_own_jail_path_does_not_shadow_it` is the
    same fact measured against real bwrap, for reachability rather than writability).
    """
    policy = FsPolicy(
        binds=(
            *WHOLE_HOST_READ_ONLY.binds,
            Bind(host_path="/decoy", jail_path=_STATE_DIR, writable=True),
        )
    )

    assert writable_shared_paths(policy, _STATE_DIR, _channels()) == (_CHANNEL_DIR,)


def test_a_channel_directory_bound_elsewhere_reports_its_host_side_location() -> None:
    """The general half of the "host equivalent" formula (TASK-0001.28's own
    correction): a jail type whose `ChannelDirectory` binds a host path at a
    *different* jail path is resolved by the bind that governs it, not by its own
    host path -- the candidate is identified in jail-path space, and what comes back is
    where that bind actually reads on the host.
    """
    channels = _channels(host_path=_CHANNEL_DIR, jail_path="/jail/side")

    assert writable_shared_paths(WHOLE_HOST_READ_ONLY, _STATE_DIR, channels) == (_CHANNEL_DIR,)
    assert declared_channel_paths(channels) == (_CHANNEL_DIR,)


def test_channels_declaring_nothing_are_not_a_channel_directory() -> None:
    """`_compile_channel_bind`'s own condition, restated: `None`, and a set declaring
    no reservation, both bind nothing -- so neither claims a writable path, and
    `declared_channel_paths` names nothing for a caller to compare against.
    """
    empty = Reservations(
        directory=ChannelDirectory(host_path=_CHANNEL_DIR, jail_path=_CHANNEL_DIR),
        reservations=(),
    )

    assert writable_shared_paths(WHOLE_HOST_READ_ONLY, _STATE_DIR, None) == ()
    assert writable_shared_paths(WHOLE_HOST_READ_ONLY, _STATE_DIR, empty) == ()
    assert declared_channel_paths(None) == ()
    assert declared_channel_paths(empty) == ()


def test_channel_exclusivity_claim_grades_unenforced_with_no_evidence() -> None:
    """AC#1's other half, moved here from the e2e battery (TASK-0001.28's review):
    `grade` reports `CHANNEL_EXCLUSIVITY_CLAIM` enforced only from evidence actually
    measured, never a hopeful default. This needs no real jail at all -- `grade` is
    already generic and already fully covered for every branch
    (`tests/unit/test_grades.py`), so the only thing left to pin here is that this
    specific claim, the one `domain/jail_types/bwrap.py` itself states, goes through
    that same generic logic the same way every other claim does.

    Belongs in `tests/unit/`, not the e2e battery: an earlier version of this pin
    lived in `tests/e2e/test_channel_exclusivity_battery.py`, whose own module-level
    `skipif(shutil.which("bwrap") is None, ...)` skipped it on every host without
    bwrap, even though grading from no evidence touches no real jail and needs none --
    its own docstring claimed it "runs on every host", which was false under that
    marker. `tests/e2e/test_claims_wiring.py`'s matching case genuinely does run
    everywhere, because that file carries no module-level skip at all; this is the
    same fact, pinned where it is actually true.
    """
    assert CHANNEL_EXCLUSIVITY_CLAIM.name == "channel_exclusivity"
    assert grade((CHANNEL_EXCLUSIVITY_CLAIM,), {}) == {CHANNEL_EXCLUSIVITY_CLAIM: Grade.UNENFORCED}
