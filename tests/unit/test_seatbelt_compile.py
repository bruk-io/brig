"""Unit tests for the Seatbelt compile (decision-0010): `compile_rules` orders the policy's rules
so SBPL's last match means what the policy means, `render_profile` turns them into the profile
`sandbox-exec` loads, with the measured header first, and `compile_supervisor_launch` wraps the
supervisor in `sandbox-exec`. Whether the kernel honours the profile is the e2e batteries'.
"""

import pytest

from brig.domain.channels import ChannelDirectory, Reservation, Reservations
from brig.domain.jail_types import seatbelt
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, FsPolicy, HostPath, PathKind

_STATE_DIR = "/state"
"""A stand-in for brig's resolved state directory."""

_SCRIPT = _STATE_DIR + "/brig-supervisor-x.py"
"""A stand-in for the supervisor script written into the state directory."""

_CHANNEL_DIR = _STATE_DIR + "/channels/abc"
"""A stand-in channel directory beneath the state directory, where the default places one."""

_CHANNELS = Reservations(
    directory=ChannelDirectory(host_path=_CHANNEL_DIR, jail_path=_CHANNEL_DIR),
    reservations=(
        Reservation(name="ctl", bound_path=_CHANNEL_DIR + "/ctl", endpoint=_CHANNEL_DIR + "/ctl"),
    ),
)

_D = PathKind.DIRECTORY
_F = PathKind.FILE
_ABSENT = PathKind.ABSENT


def _same(*paths: str, kind: PathKind = _D) -> dict[str, HostPath]:
    """Host facts for paths that resolve to themselves."""
    return {path: HostPath(kind, path) for path in paths}


def _profile(
    policy: FsPolicy,
    host: dict[str, HostPath],
    *,
    channels: Reservations | None = None,
    egress_port: int | None = None,
) -> list[str]:
    rules = seatbelt.compile_rules(
        policy,
        host,
        state_dir=_STATE_DIR,
        supervisor_script=_SCRIPT,
        channels=channels,
        egress_port=egress_port,
    )
    return seatbelt.render_profile(rules).splitlines()


def test_the_header_denies_by_default_and_imports_no_system_profile() -> None:
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/"))

    assert lines[:2] == ["(version 1)", "(deny default)"]
    assert not any("import" in line for line in lines)


def test_signals_reach_only_the_jail_s_own_sandbox() -> None:
    """Unfiltered `signal` let a jail kill a host process (measured, TASK-0061)."""
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/"))

    signal_lines = [line for line in lines if "signal" in line]
    assert signal_lines == ["(allow signal (target same-sandbox))"]


def test_no_system_call_is_refused_by_number() -> None:
    """Refusing `setsid` and `setpgid` held nothing (`posix_spawn` left the group anyway), and
    cost daemons their session; teardown finds the jail's processes by the mark instead."""
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/"))

    assert not any("syscall" in line for line in lines)


def test_the_member_mark_alone_is_visible_inside_the_state_directory() -> None:
    mark = _STATE_DIR + "/brig-supervisor-x.mark"
    rules = seatbelt.compile_rules(
        WHOLE_HOST_READ_ONLY,
        _same("/", _STATE_DIR),
        state_dir=_STATE_DIR,
        supervisor_script=_SCRIPT,
        member_mark=mark,
    )
    lines = seatbelt.render_profile(rules).splitlines()

    state_mask = lines.index(f'(deny file-read* file-write* (subpath "{_STATE_DIR}"))')
    allowed = lines.index(f'(allow file-read-metadata (literal "{mark}"))')
    assert state_mask < allowed
    assert not any("brig-supervisor-x.decoy" in line for line in lines)


def test_only_the_directory_lookup_mach_service_is_allowed() -> None:
    """Unfiltered `mach-lookup` let a jail read the host's pasteboard (measured, TASK-0061)."""
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/"))

    mach_lines = [line for line in lines if "mach-" in line]
    assert mach_lines == [
        '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo"))'
    ]


def test_dev_is_writable_only_at_its_null_and_zero_devices_and_own_descriptors() -> None:
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/"))

    dev_writes = [line for line in lines if "/dev" in line and "write" in line]
    assert dev_writes == [
        '(allow file-read* file-write-data (literal "/dev/null") (literal "/dev/zero") '
        '(literal "/dev/stdin") (literal "/dev/stdout") (literal "/dev/stderr") '
        '(subpath "/dev/fd"))'
    ]
    assert not any("file-ioctl" in line for line in lines)


def test_a_write_deny_follows_the_writable_root_it_carves_out_of() -> None:
    policy = FsPolicy(readable=("/",), writable=("/w",), write_denies=("/w/.git",))
    lines = _profile(policy, _same("/", "/w", "/w/.git"))

    writable = lines.index('(allow file-read* file-write* (subpath "/w"))')
    deny = lines.index('(deny file-write* (subpath "/w/.git"))')
    assert writable < deny


def test_a_mask_follows_the_root_it_hides_a_path_in() -> None:
    policy = FsPolicy(readable=("/w",), masks=("/w/secret.env",))
    lines = _profile(policy, {**_same("/w"), **_same("/w/secret.env", kind=_F)})

    readable = lines.index('(allow file-read* (subpath "/w"))')
    mask = lines.index('(deny file-read* file-write* (subpath "/w/secret.env"))')
    assert readable < mask


def test_a_readable_root_nested_in_a_writable_one_is_denied_writes() -> None:
    policy = FsPolicy(writable=("/w",), readable=("/w/ro",))
    lines = _profile(policy, _same("/w", "/w/ro"))

    allow = lines.index('(allow file-read* (subpath "/w/ro"))')
    deny = lines.index('(deny file-write* (subpath "/w/ro"))')
    assert lines.index('(allow file-read* file-write* (subpath "/w"))') < allow < deny


def test_every_directory_between_a_writable_root_and_a_carve_out_is_pinned() -> None:
    """A rename is judged by its paths, so an unpinned directory on the way carries a carve-out
    out from under its rule (old SPEC decision-207); the root itself too (decision-208)."""
    policy = FsPolicy(readable=("/",), writable=("/w",), write_denies=("/w/a/b/deny",))
    lines = _profile(policy, _same("/", "/w", "/w/a", "/w/a/b", "/w/a/b/deny"))

    pins = [line for line in lines if line.startswith("(deny file-write-unlink")]
    assert pins == [
        '(deny file-write-unlink (literal "/w"))',
        '(deny file-write-unlink (literal "/w/a"))',
        '(deny file-write-unlink (literal "/w/a/b"))',
    ]


def test_an_absent_directory_on_the_way_to_an_absent_carve_out_is_pinned() -> None:
    """brig makes it before the jail starts (old SPEC decision-208): a rename onto an absent
    path is a create, which no pin refuses."""
    policy = FsPolicy(readable=("/",), writable=("/w",), masks=("/w/new/secret",))
    host = {
        **_same("/", "/w"),
        "/w/new": HostPath(_ABSENT, "/w/new"),
        "/w/new/secret": HostPath(_ABSENT, "/w/new/secret"),
    }
    lines = _profile(policy, host)

    assert '(deny file-write-unlink (literal "/w/new"))' in lines


def test_a_root_reached_through_a_link_is_ruled_at_both_paths() -> None:
    """Seatbelt matches the path a lookup resolves to (`/tmp` is `/private/tmp` on Darwin)."""
    policy = FsPolicy(readable=("/",), writable=("/tmp/w",), masks=("/tmp/w/secret",))
    host = {
        **_same("/"),
        "/tmp/w": HostPath(_D, "/private/tmp/w"),
        "/tmp/w/secret": HostPath(_F, "/private/tmp/w/secret"),
    }
    lines = _profile(policy, host)

    for path in ("/tmp/w", "/private/tmp/w"):
        assert f'(allow file-read* file-write* (subpath "{path}"))' in lines
    for path in ("/tmp/w/secret", "/private/tmp/w/secret"):
        assert f'(deny file-read* file-write* (subpath "{path}"))' in lines


def test_brig_s_state_directory_is_masked_after_every_policy_rule() -> None:
    policy = FsPolicy(readable=("/",), writable=("/",))
    lines = _profile(policy, _same("/", _STATE_DIR))

    mask = lines.index(f'(deny file-read* file-write* (subpath "{_STATE_DIR}"))')
    assert mask > lines.index('(allow file-read* file-write* (subpath "/"))')


def test_the_supervisor_script_alone_is_readable_inside_the_state_directory() -> None:
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/", _STATE_DIR))

    mask = lines.index(f'(deny file-read* file-write* (subpath "{_STATE_DIR}"))')
    script = lines.index(f'(allow file-read* (subpath "{_SCRIPT}"))')
    assert mask < script


def test_the_channel_directory_is_writable_and_the_only_unix_socket_place() -> None:
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/", _STATE_DIR), channels=_CHANNELS)

    mask = lines.index(f'(deny file-read* file-write* (subpath "{_STATE_DIR}"))')
    writable = lines.index(f'(allow file-read* file-write* (subpath "{_CHANNEL_DIR}"))')
    network = [line for line in lines if "network" in line]
    assert mask < writable
    assert network == [f'(allow network-bind network-outbound (subpath "{_CHANNEL_DIR}"))']


def test_no_channel_and_no_egress_allows_no_network_operation() -> None:
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/"))

    assert not any("network" in line for line in lines)


def test_egress_allows_outbound_only_to_the_bridge_port_never_from_it() -> None:
    """An outbound rule filtered on the local port let a jail bind its source port to the
    bridge's and connect anywhere (measured, TASK-0061)."""
    lines = _profile(WHOLE_HOST_READ_ONLY, _same("/"), egress_port=3128)

    network = [line for line in lines if "network" in line]
    assert network == [
        '(allow network-bind network-inbound (local tcp "localhost:3128"))',
        '(allow network-outbound (remote tcp "localhost:3128"))',
    ]


def test_a_quote_or_backslash_in_a_path_cannot_end_its_string() -> None:
    policy = FsPolicy(readable=('/odd"dir\\x',))
    lines = _profile(policy, _same('/odd"dir\\x'))

    assert '(allow file-read* (subpath "/odd\\"dir\\\\x"))' in lines


def test_a_nul_byte_in_a_path_is_refused() -> None:
    with pytest.raises(ValueError, match="NUL"):
        _profile(FsPolicy(readable=("/a\x00b",)), _same("/a\x00b"))


def test_the_supervisor_runs_under_sandbox_exec_with_the_profile() -> None:
    argv = seatbelt.compile_supervisor_launch(("/py", "-I", _SCRIPT), "/state/p.sb")

    assert argv == ("/usr/bin/sandbox-exec", "-f", "/state/p.sb", "/py", "-I", _SCRIPT)


def test_a_cwd_is_entered_by_the_interpreter_before_the_supervisor_runs() -> None:
    argv = seatbelt.compile_supervisor_launch(("/py", "-I", _SCRIPT), "/state/p.sb", "/work")

    assert argv[:5] == ("/usr/bin/sandbox-exec", "-f", "/state/p.sb", "/py", "-I")
    assert argv[5] == "-c"
    assert argv[-2:] == ("/work", _SCRIPT)
