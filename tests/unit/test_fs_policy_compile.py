"""Unit tests for the filesystem policy (decision-0007): `refusal` over an `FsPolicy`, and
bwrap's `compile_mounts`, which turns one into ordered mounts, the more specific path last."""

from brig.domain.jail_types.bwrap import Mount, MountKind, compile_mounts, render
from brig.domain.policy.paths import (
    FsPolicy,
    HostPath,
    MaskHides,
    PathKind,
    PathNotAbsolute,
    RootAbsent,
    ThroughLink,
    refusal,
)

_STATE = "/state"
_SCRIPT = "/state/brig-supervisor-x.py"
_EMPTY = "/state/empty"
_BRIGS_OWN = (
    Mount(MountKind.TMPFS, _STATE),
    Mount(MountKind.READ_ONLY, _SCRIPT, _SCRIPT),
    Mount(MountKind.REMOUNT_READ_ONLY, _STATE),
)


def _policy_mounts(policy: FsPolicy, kinds: dict[str, PathKind]) -> tuple[Mount, ...]:
    """The policy's own mounts, without brig's state-directory mounts that end every jail."""
    mounts = compile_mounts(
        policy, kinds, state_dir=_STATE, supervisor_script=_SCRIPT, empty_dir=_EMPTY
    )
    assert mounts[-3:] == _BRIGS_OWN
    return mounts[:-3]


def test_entries_mount_shallowest_first_so_the_more_specific_wins() -> None:
    policy = FsPolicy(
        readable=("/usr",),
        writable=("/w",),
        write_denies=("/w/.git/hooks",),
        masks=("/w/secret.env", "/w/keys"),
    )
    kinds = {
        "/w/.git/hooks": PathKind.DIRECTORY,
        "/w/secret.env": PathKind.FILE,
        "/w/keys": PathKind.DIRECTORY,
    }

    assert _policy_mounts(policy, kinds) == (
        Mount(MountKind.READ_ONLY, "/usr", "/usr"),
        Mount(MountKind.WRITABLE, "/w", "/w"),
        Mount(MountKind.READ_ONLY, "/w/keys", _EMPTY),
        Mount(MountKind.READ_ONLY, "/w/secret.env", "/dev/null"),
        Mount(MountKind.READ_ONLY, "/w/.git/hooks", "/w/.git/hooks"),
    )


def test_at_one_path_a_mask_mounts_after_a_deny_after_a_root() -> None:
    policy = FsPolicy(writable=("/w",), write_denies=("/w/x",), masks=("/w/x",))

    mounts = _policy_mounts(policy, {"/w/x": PathKind.FILE})

    assert mounts[-2:] == (
        Mount(MountKind.READ_ONLY, "/w/x", "/w/x"),
        Mount(MountKind.READ_ONLY, "/w/x", "/dev/null"),
    )


def test_an_absent_deny_or_mask_under_a_writable_root_is_held_by_the_empty_directory() -> None:
    """The command could create either there, so each gets an empty read-only directory."""
    policy = FsPolicy(writable=("/w",), write_denies=("/w/.envrc",), masks=("/w/token",))

    assert _policy_mounts(policy, {}) == (
        Mount(MountKind.WRITABLE, "/w", "/w"),
        Mount(MountKind.READ_ONLY, "/w/.envrc", _EMPTY),
        Mount(MountKind.READ_ONLY, "/w/token", _EMPTY),
    )


def test_what_needs_no_mount_gets_none() -> None:
    """A deny outside every writable root is read-only already; an absent mask outside one
    cannot be created; a deny or mask inside a mask is hidden already."""
    policy = FsPolicy(
        readable=("/",),
        writable=("/w",),
        write_denies=("/etc/passwd", "/w/keys/inner"),
        masks=("/home/absent", "/w/keys", "/w/keys/deeper"),
    )
    kinds = {
        "/etc/passwd": PathKind.FILE,
        "/w/keys": PathKind.DIRECTORY,
        "/w/keys/inner": PathKind.FILE,
        "/w/keys/deeper": PathKind.FILE,
    }

    assert _policy_mounts(policy, kinds) == (
        Mount(MountKind.READ_ONLY, "/", "/"),
        Mount(MountKind.WRITABLE, "/w", "/w"),
        Mount(MountKind.READ_ONLY, "/w/keys", _EMPTY),
    )


def test_a_present_mask_outside_every_writable_root_is_still_masked() -> None:
    policy = FsPolicy(readable=("/",), masks=("/home/me/.ssh",))

    mounts = _policy_mounts(policy, {"/home/me/.ssh": PathKind.DIRECTORY})

    assert mounts[-1] == Mount(MountKind.READ_ONLY, "/home/me/.ssh", _EMPTY)


def test_render_spells_each_mount_as_bwraps_flags() -> None:
    mounts = (
        Mount(MountKind.READ_ONLY, "/a", "/src"),
        Mount(MountKind.WRITABLE, "/b", "/b"),
        Mount(MountKind.TMPFS, "/c"),
        Mount(MountKind.REMOUNT_READ_ONLY, "/c"),
    )

    assert render(mounts) == (
        "--ro-bind",
        "/src",
        "/a",
        "--bind",
        "/b",
        "/b",
        "--tmpfs",
        "/c",
        "--remount-ro",
        "/c",
    )


def test_a_policy_with_only_absolute_normal_paths_and_no_hiding_mask_is_not_refused() -> None:
    policy = FsPolicy(readable=("/",), writable=("/w",), masks=("/w/secret",))

    assert refusal(policy, needed=(_STATE,)) is None


def test_a_relative_or_unnormalised_path_is_refused() -> None:
    for path in ("w", "/w/../etc", "/w//x", "/w/./x", "/w/"):
        assert refusal(FsPolicy(writable=(path,))) == PathNotAbsolute(path), path


def test_a_mask_hiding_a_root_or_a_path_brig_needs_is_refused() -> None:
    assert refusal(FsPolicy(writable=("/home/me/p",), masks=("/home/me",))) == MaskHides(
        "/home/me", "/home/me/p"
    )
    assert refusal(FsPolicy(readable=("/",), masks=("/root",)), needed=("/root/.brig",)) == (
        MaskHides("/root", "/root/.brig")
    )


def test_an_absent_entry_whose_parent_is_read_only_in_the_jail_needs_no_mount() -> None:
    """TASK-0026: under a readable root or a present deny nested in a writable root, the command
    cannot create the absent entry, and bwrap could not mount on a read-only bind."""
    policy = FsPolicy(
        readable=("/w/ro",),
        writable=("/w",),
        write_denies=("/w/d", "/w/ro/absent", "/w/d/absent"),
    )

    assert _policy_mounts(policy, {"/w/d": PathKind.DIRECTORY}) == (
        Mount(MountKind.WRITABLE, "/w", "/w"),
        Mount(MountKind.READ_ONLY, "/w/ro", "/w/ro"),
        Mount(MountKind.READ_ONLY, "/w/d", "/w/d"),
    )


def test_a_root_absent_on_the_host_is_refused() -> None:
    host = {"/w": HostPath(PathKind.ABSENT, "/w")}

    assert refusal(FsPolicy(writable=("/w",)), host=host) == RootAbsent("/w")


def test_an_entry_reached_through_a_link_inside_a_writable_root_is_refused() -> None:
    """TASK-0025: `/w/hooks` resolves to `/w/real`, a link inside the writable root `/w`."""
    host = {
        "/w": HostPath(PathKind.DIRECTORY, "/w"),
        "/w/hooks": HostPath(PathKind.DIRECTORY, "/w/real"),
    }
    policy = FsPolicy(writable=("/w",), write_denies=("/w/hooks",))

    assert refusal(policy, host=host) == ThroughLink("/w/hooks", "/w")


def test_a_link_above_the_writable_root_is_not_a_refusal() -> None:
    """The command cannot change a link outside every writable root, so `/w` being reached
    through one (here `/w` -> `/data/w`) refuses nothing beneath it."""
    host = {
        "/w": HostPath(PathKind.DIRECTORY, "/data/w"),
        "/w/hooks": HostPath(PathKind.DIRECTORY, "/data/w/hooks"),
        "/w/secret": HostPath(PathKind.ABSENT, "/data/w/secret"),
    }
    policy = FsPolicy(writable=("/w",), write_denies=("/w/hooks",), masks=("/w/secret",))

    assert refusal(policy, host=host) is None
