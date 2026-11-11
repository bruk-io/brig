"""Unit tests for the Seatbelt compile's ceilings (decision-0008, decision-0010 item 4): the
strongest grade each claim can have, read from the compiled rules before any jail runs. The
e2e battery `test_seatbelt_battery.py` holds each to what it measures."""

from brig.domain.channels import ChannelDirectory, Reservation, Reservations
from brig.domain.grades import Grade
from brig.domain.jail_types import seatbelt
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, FsPolicy, HostPath, PathKind

_STATE_DIR = "/state"
_SCRIPT = _STATE_DIR + "/brig-supervisor-x.py"
_CHANNEL_DIR = _STATE_DIR + "/channels/abc"
_CHANNELS = Reservations(
    directory=ChannelDirectory(host_path=_CHANNEL_DIR, jail_path=_CHANNEL_DIR),
    reservations=(
        Reservation(name="ctl", bound_path=_CHANNEL_DIR + "/ctl", endpoint=_CHANNEL_DIR + "/ctl"),
    ),
)


def _ceilings(
    policy: FsPolicy, *, channels: Reservations | None = None, egress: bool = False
) -> dict[str, Grade]:
    paths = (*policy.readable, *policy.writable, *policy.write_denies, *policy.masks)
    host = {path: HostPath(PathKind.DIRECTORY, path) for path in paths}
    rules = seatbelt.compile_rules(
        policy,
        host,
        state_dir=_STATE_DIR,
        supervisor_script=_SCRIPT,
        channels=channels,
        egress_port=3128 if egress else None,
    )
    return {
        claim.name: grade
        for claim, grade in seatbelt.ceilings(rules, channels, egress=egress).items()
    }


def test_writes_confined_to_a_root_with_nothing_carved_out_are_enforced() -> None:
    ceilings = _ceilings(FsPolicy(readable=("/",), writable=("/w",)))

    assert ceilings["fs_write"] is Grade.ENFORCED


def test_a_write_deny_beneath_a_writable_root_makes_writes_best_effort() -> None:
    ceilings = _ceilings(FsPolicy(readable=("/",), writable=("/w",), write_denies=("/w/.git",)))

    assert ceilings["fs_write"] is Grade.BEST_EFFORT


def test_brig_s_state_directory_beneath_a_writable_root_makes_writes_best_effort() -> None:
    ceilings = _ceilings(FsPolicy(readable=("/",), writable=("/",)))

    assert ceilings["fs_write"] is Grade.BEST_EFFORT


def test_reads_are_best_effort_whatever_the_policy() -> None:
    assert _ceilings(FsPolicy(readable=("/w",)))["fs_read"] is Grade.BEST_EFFORT
    assert _ceilings(WHOLE_HOST_READ_ONLY)["fs_read"] is Grade.BEST_EFFORT


def test_no_egress_policy_enforces_the_network_claim() -> None:
    ceilings = _ceilings(WHOLE_HOST_READ_ONLY)

    assert ceilings["network"] is Grade.ENFORCED


def test_an_egress_policy_states_the_egress_claim_best_effort() -> None:
    policy = WHOLE_HOST_READ_ONLY
    rules = seatbelt.compile_rules(
        policy,
        {"/": HostPath(PathKind.DIRECTORY, "/")},
        state_dir=_STATE_DIR,
        supervisor_script=_SCRIPT,
        egress_port=3128,
    )
    report = seatbelt.ceilings(rules, None, egress=True)

    assert report[seatbelt.SEATBELT_NETWORK_EGRESS_CLAIM] is Grade.BEST_EFFORT
    assert seatbelt.SEATBELT_NETWORK_CLAIM not in report


def test_a_writable_root_shared_with_the_host_violates_channel_exclusivity() -> None:
    ceilings = _ceilings(FsPolicy(readable=("/",), writable=("/w",)), channels=_CHANNELS)

    assert ceilings["channel_exclusivity"] is Grade.VIOLATED


def test_a_readable_host_and_a_declared_channel_keep_channel_exclusivity_enforced() -> None:
    """Seatbelt refuses a dial of a host socket inside a readable root, so reading the whole
    host lowers nothing, unlike a bind mount."""
    ceilings = _ceilings(WHOLE_HOST_READ_ONLY, channels=_CHANNELS)

    assert ceilings["channel_exclusivity"] is Grade.ENFORCED


def test_the_environment_claim_is_enforced() -> None:
    assert _ceilings(WHOLE_HOST_READ_ONLY)["env"] is Grade.ENFORCED
