"""Integration test for channel reservations (TASK-0001.25 AC#3): through brig's
public API, with the world faked at infra's edge, a reservation's endpoint is known
before the jail is created and reaches the jailed command only through argv -- never
through the environment `StartSupervisedCommand` carries to the supervisor (old SPEC
decision-184/186).

`FakeSupervisors.start` records the `(argv, env)` the driver performed
`StartSupervisedCommand` with, so the assertions read exactly what would have crossed
to the supervisor.
"""

from pathlib import Path

import pytest
from tests.integration.fakes import (
    FakeChannelDirectories,
    FakeProcesses,
    FakeSupervisors,
    plant_fake_proc,
)

from brig import (
    Channel,
    ChannelNameRefused,
    EnvPolicy,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
)


def test_a_reservation_reaches_the_command_through_argv_and_never_through_env(
    tmp_path: Path,
) -> None:
    """`reserve_channels` hands back the endpoint before anything starts; the caller
    writes it into `command`; the supervisor is started with it in argv, and neither
    the endpoint nor the bound path appears anywhere in the env it was handed -- even
    with an `EnvPolicy` that also allows the names a reservation would plausibly be
    smuggled in under (`BRIG_CHANNEL_CTL`, `CTL`), so such an injection would survive
    the scrub and reach the recorded env rather than being silently removed by it.

    TASK-0001.27: a channel-declaring create also scans for the jail's PID namespace;
    `proc_root` points that scan at a tree this test plants, so no real bwrap is
    needed (the same seam `infra.processes.group_alive` carries).
    """
    directories = FakeChannelDirectories()
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    proc_root = str(tmp_path / "proc")
    plant_fake_proc(proc_root, {2000: (1, "2000"), 2001: (2000, "2001\t1")})

    reserved = reserve_channels((Channel("ctl"),), directories=directories)
    (reservation,) = reserved.reservations
    assert supervisors.started == []  # nothing has started yet

    command = ("server", "--listen", reservation.endpoint)
    host_like_env = (("PATH", "/usr/bin"), ("HOME", "/home/x"))
    jail = create_bwrap_jail(
        command,
        env=host_like_env,
        env_policy=EnvPolicy(allowed=("PATH", "HOME", "BRIG_CHANNEL_CTL", "CTL")),
        channels=reserved,
        processes=processes,
        supervisors=supervisors,
        directories=directories,
        proc_root=proc_root,
    )
    destroy_jail(jail, processes=processes, supervisors=supervisors, directories=directories)

    assert reservation.endpoint == "/fake/state/channels/0001/ctl"
    assert directories.allocated == 1
    [(argv, env)] = supervisors.started
    assert argv == command
    assert env == host_like_env
    for path in (reservation.endpoint, reservation.bound_path):
        for name, value in env:
            assert path not in name
            assert path not in value


def test_a_refused_channel_name_raises_before_anything_starts() -> None:
    """A name that would escape the channel directory raises `ChannelNameRefused`
    from `reserve_channels`, so the caller never reaches `create_bwrap_jail`.
    """
    directories = FakeChannelDirectories()

    with pytest.raises(ChannelNameRefused) as exc_info:
        reserve_channels((Channel("../escape"),), directories=directories)

    assert exc_info.value.name == "../escape"
