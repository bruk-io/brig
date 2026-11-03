"""Unit tests for decision-0008: the grade ceiling bwrap's compile states for each claim of a
jail, before it runs, and `at_most`, which a battery holds a report to."""

from brig.domain.grades import Grade, at_most
from brig.domain.jail_types.bwrap import (
    CHANNEL_EXCLUSIVITY_CLAIM,
    ENV_CLAIM,
    FS_READ_CLAIM,
    FS_WRITE_CLAIM,
    NETWORK_CLAIM,
    ceilings,
    compile_mounts,
)
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, FsPolicy, PathKind


def _ceilings(policy: FsPolicy, kinds: dict[str, PathKind]) -> dict[str, Grade]:
    mounts = compile_mounts(
        policy, kinds, state_dir="/s", supervisor_script="/s/x.py", empty_dir="/s/empty"
    )
    return {claim.name: grade for claim, grade in ceilings(policy, mounts, None).items()}


def test_the_default_policy_states_every_claim_enforced() -> None:
    assert _ceilings(WHOLE_HOST_READ_ONLY, {}) == {
        FS_WRITE_CLAIM.name: Grade.ENFORCED,
        FS_READ_CLAIM.name: Grade.ENFORCED,
        NETWORK_CLAIM.name: Grade.ENFORCED,
        ENV_CLAIM.name: Grade.ENFORCED,
        CHANNEL_EXCLUSIVITY_CLAIM.name: Grade.ENFORCED,
    }


def test_a_deny_or_mask_inside_a_writable_root_is_only_best_effort() -> None:
    """The host replacing the entry a deny or mask is mounted on detaches it in the jail."""
    policy = FsPolicy(
        readable=("/",), writable=("/w",), write_denies=("/w/hooks",), masks=("/w/secret",)
    )
    found = _ceilings(policy, {"/w/hooks": PathKind.DIRECTORY, "/w/secret": PathKind.FILE})

    assert found[FS_WRITE_CLAIM.name] is Grade.BEST_EFFORT
    assert found[FS_READ_CLAIM.name] is Grade.BEST_EFFORT


def test_a_mask_outside_every_writable_root_keeps_fs_read_enforced() -> None:
    policy = FsPolicy(readable=("/",), writable=("/w",), masks=("/home/me/.ssh",))
    found = _ceilings(policy, {"/home/me/.ssh": PathKind.DIRECTORY})

    assert found[FS_READ_CLAIM.name] is Grade.ENFORCED


def test_a_writable_root_shared_with_the_host_violates_channel_exclusivity() -> None:
    found = _ceilings(FsPolicy(readable=("/",), writable=("/w",)), {})

    assert found[CHANNEL_EXCLUSIVITY_CLAIM.name] is Grade.VIOLATED


def test_at_most_orders_the_grades_strongest_first() -> None:
    order = [Grade.ENFORCED, Grade.BEST_EFFORT, Grade.UNENFORCED, Grade.VIOLATED]
    for i, stated in enumerate(order):
        for j, measured in enumerate(order):
            assert at_most(stated, measured) == (i >= j), (stated, measured)
