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


def test_the_default_policy_shows_the_hosts_socket_places_so_exclusivity_is_violated() -> None:
    """`/` covers `/run`, `/tmp` and the rest, whose sockets the jail could dial, and a socket
    it can dial can carry the network (TASK-0043)."""
    assert _ceilings(WHOLE_HOST_READ_ONLY, {}) == {
        FS_WRITE_CLAIM.name: Grade.ENFORCED,
        FS_READ_CLAIM.name: Grade.ENFORCED,
        NETWORK_CLAIM.name: Grade.VIOLATED,
        ENV_CLAIM.name: Grade.ENFORCED,
        CHANNEL_EXCLUSIVITY_CLAIM.name: Grade.VIOLATED,
    }


def test_a_policy_showing_no_listed_socket_place_is_still_only_best_effort() -> None:
    """TASK-0043: a root that is no listed socket place still shows host directories a socket
    could sit in (an agent's, under a home directory); a list of places is not a mechanism."""
    assert _ceilings(FsPolicy(readable=("/usr", "/etc")), {})[CHANNEL_EXCLUSIVITY_CLAIM.name] is (
        Grade.BEST_EFFORT
    )
    masked = FsPolicy(readable=("/",), masks=("/run", "/var/run", "/tmp", "/var/tmp", "/dev/shm"))
    kinds = {path: PathKind.DIRECTORY for path in masked.masks}
    assert _ceilings(masked, kinds)[CHANNEL_EXCLUSIVITY_CLAIM.name] is Grade.BEST_EFFORT
    assert (
        _ceilings(FsPolicy(readable=("/home/me/.gnupg",)), {})[CHANNEL_EXCLUSIVITY_CLAIM.name]
        is Grade.BEST_EFFORT
    )


def test_only_a_jail_that_sees_no_host_path_keeps_exclusivity_enforced() -> None:
    """No root at all: the jail sees brig's own mounts, its `/proc` and `/dev`, and nothing of
    the host's. (`interpreter_refusal` refuses such a policy before a jail starts.)"""
    found = _ceilings(FsPolicy(), {})

    assert found[CHANNEL_EXCLUSIVITY_CLAIM.name] is Grade.ENFORCED
    assert found[NETWORK_CLAIM.name] is Grade.ENFORCED


def test_a_root_inside_a_socket_place_is_dialable_too() -> None:
    found = _ceilings(FsPolicy(readable=("/usr", "/run/user/1000/app")), {})
    assert found[CHANNEL_EXCLUSIVITY_CLAIM.name] is Grade.VIOLATED


def test_a_deny_or_mask_inside_a_writable_root_is_only_best_effort() -> None:
    """The host replacing the entry a deny or mask is mounted on detaches it in the jail."""
    policy = FsPolicy(
        readable=("/",), writable=("/w",), write_denies=("/w/hooks",), masks=("/w/secret",)
    )
    found = _ceilings(policy, {"/w/hooks": PathKind.DIRECTORY, "/w/secret": PathKind.FILE})

    assert found[FS_WRITE_CLAIM.name] is Grade.BEST_EFFORT
    assert found[FS_READ_CLAIM.name] is Grade.BEST_EFFORT


def test_a_mask_outside_every_writable_root_is_best_effort_too() -> None:
    """The host can rename over a masked entry wherever it is; outside every writable root, its
    replacement is read-only to the jail, so `fs_write` keeps its grade."""
    policy = FsPolicy(readable=("/",), writable=("/w",), masks=("/home/me/.ssh",))
    found = _ceilings(policy, {"/home/me/.ssh": PathKind.DIRECTORY})

    assert found[FS_READ_CLAIM.name] is Grade.BEST_EFFORT
    assert found[FS_WRITE_CLAIM.name] is Grade.ENFORCED


def test_a_readable_root_nested_in_a_writable_root_caps_fs_write_at_best_effort() -> None:
    """TASK-0043: the host renaming `W/vendor` away and making a new one leaves the jail writing
    there through `W`. Read from the compiled mounts, so the pins on the way (writable over
    writable) are not what caps it."""
    policy = FsPolicy(readable=("/", "/w/a/vendor"), writable=("/w",))
    kinds = {"/w/a": PathKind.DIRECTORY}

    assert _ceilings(policy, kinds)[FS_WRITE_CLAIM.name] is Grade.BEST_EFFORT


def test_a_mask_inside_a_writable_root_caps_fs_write_too() -> None:
    policy = FsPolicy(readable=("/",), writable=("/w",), masks=("/w/secret",))

    found = _ceilings(policy, {"/w/secret": PathKind.FILE})

    assert found[FS_WRITE_CLAIM.name] is Grade.BEST_EFFORT


def test_a_writable_root_inside_another_or_over_a_readable_one_keeps_fs_write() -> None:
    """Writable over writable (a pin, a nested writable root) and writable over read-only mount
    nothing read-only beneath a writable one."""
    policy = FsPolicy(readable=("/",), writable=("/w", "/w/inner"))

    assert _ceilings(policy, {})[FS_WRITE_CLAIM.name] is Grade.ENFORCED


def test_network_is_never_stronger_than_channel_exclusivity() -> None:
    """TASK-0043 AC#3: a host socket the jail can dial can carry the network, so whatever
    `channel_exclusivity` comes to, `network` is no stronger."""
    policies: tuple[tuple[FsPolicy, dict[str, PathKind]], ...] = (
        (FsPolicy(), {}),
        (FsPolicy(readable=("/usr",)), {}),
        (FsPolicy(readable=("/usr",), writable=("/w",)), {}),
        (WHOLE_HOST_READ_ONLY, {}),
        (
            FsPolicy(readable=("/",), masks=("/run", "/tmp")),
            {
                "/run": PathKind.DIRECTORY,
                "/tmp": PathKind.DIRECTORY,
            },
        ),
    )
    seen: set[Grade] = set()
    for policy, kinds in policies:
        found = _ceilings(policy, kinds)
        exclusivity = found[CHANNEL_EXCLUSIVITY_CLAIM.name]
        seen.add(exclusivity)
        assert at_most(found[NETWORK_CLAIM.name], exclusivity), (policy, found)
    assert seen == {Grade.ENFORCED, Grade.BEST_EFFORT, Grade.VIOLATED}


def test_no_deny_or_mask_keeps_fs_read_and_fs_write_enforced() -> None:
    found = _ceilings(FsPolicy(readable=("/",), writable=("/w",)), {})

    assert (found[FS_READ_CLAIM.name], found[FS_WRITE_CLAIM.name]) == (
        Grade.ENFORCED,
        Grade.ENFORCED,
    )


def test_a_writable_root_shared_with_the_host_violates_channel_exclusivity() -> None:
    found = _ceilings(FsPolicy(readable=("/usr",), writable=("/w",)), {})

    assert found[CHANNEL_EXCLUSIVITY_CLAIM.name] is Grade.VIOLATED


def test_at_most_orders_the_grades_strongest_first() -> None:
    order = [Grade.ENFORCED, Grade.BEST_EFFORT, Grade.UNENFORCED, Grade.VIOLATED]
    for i, stated in enumerate(order):
        for j, measured in enumerate(order):
            assert at_most(stated, measured) == (i >= j), (stated, measured)
