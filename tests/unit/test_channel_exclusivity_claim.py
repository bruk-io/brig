"""Unit tests for the `channel_exclusivity` claim's enumeration: `writable_shared_paths` over
the mounts a jail was compiled with, and `declared_channel_paths`. Pure: literal mounts in,
literal tuples out.

The case that tells a real enumeration from a filter on writable binds is a writable root a
later mount replaces at its own path: the jail cannot write there, so it is not shared.
"""

from brig.domain.channels import ChannelDirectory, Reservation, Reservations
from brig.domain.grades import Grade, grade
from brig.domain.jail_types.bwrap import (
    CHANNEL_EXCLUSIVITY_CLAIM,
    compile_mounts,
    declared_channel_paths,
    writable_shared_paths,
)
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, FsPolicy, PathKind

_STATE_DIR = "/state/brig"
_CHANNEL_DIR = _STATE_DIR + "/channels/abc"


def _channels(reservations: bool = True) -> Reservations:
    return Reservations(
        directory=ChannelDirectory(host_path=_CHANNEL_DIR, jail_path=_CHANNEL_DIR),
        reservations=(
            (
                Reservation(
                    name="ctl", bound_path=_CHANNEL_DIR + "/ctl", endpoint=_CHANNEL_DIR + "/ctl"
                ),
            )
            if reservations
            else ()
        ),
    )


def _shared(
    policy: FsPolicy,
    channels: Reservations | None = None,
    kinds: dict[str, PathKind] | None = None,
) -> tuple[str, ...]:
    mounts = compile_mounts(
        policy,
        kinds or {},
        state_dir=_STATE_DIR,
        supervisor_script=_STATE_DIR + "/brig-supervisor-x.py",
        empty_dir=_STATE_DIR + "/empty",
        channels=channels,
    )
    return writable_shared_paths(mounts)


def test_no_channels_under_the_default_policy_shares_nothing_writable() -> None:
    assert _shared(WHOLE_HOST_READ_ONLY) == ()


def test_declared_channels_share_exactly_the_channel_directory() -> None:
    assert _shared(WHOLE_HOST_READ_ONLY, _channels()) == (_CHANNEL_DIR,)
    assert declared_channel_paths(_channels()) == (_CHANNEL_DIR,)


def test_a_policys_writable_root_is_reported_alongside_the_channel_directory() -> None:
    policy = FsPolicy(readable=("/",), writable=("/work",))

    assert _shared(policy, _channels()) == ("/work", _CHANNEL_DIR)


def test_a_writable_root_a_later_mount_replaces_at_its_own_path_is_not_shared() -> None:
    """A write deny at a writable root's own path mounts after it, read-only, so the jail
    cannot write there: not shared, though the policy names it writable."""
    policy = FsPolicy(readable=("/",), writable=("/work",), write_denies=("/work",))

    assert _shared(policy, kinds={"/work": PathKind.DIRECTORY}) == ()


def test_the_state_directory_is_never_reported_even_when_a_policy_names_it_writable() -> None:
    """The state directory's tmpfs mounts after the policy's roots and is sealed read-only,
    so a writable root at its path does not survive (TASK-0019)."""
    policy = FsPolicy(readable=("/",), writable=(_STATE_DIR,))

    assert _shared(policy) == ()


def test_channels_declaring_nothing_are_not_a_channel_directory() -> None:
    assert _shared(WHOLE_HOST_READ_ONLY, _channels(reservations=False)) == ()
    assert declared_channel_paths(_channels(reservations=False)) == ()
    assert declared_channel_paths(None) == ()


def test_channel_exclusivity_claim_grades_unenforced_with_no_evidence() -> None:
    """The claim the compile states goes through the generic `grade`, never enforced by
    default."""
    assert CHANNEL_EXCLUSIVITY_CLAIM.name == "channel_exclusivity"
    assert grade((CHANNEL_EXCLUSIVITY_CLAIM,), {}) == {CHANNEL_EXCLUSIVITY_CLAIM: Grade.UNENFORCED}
