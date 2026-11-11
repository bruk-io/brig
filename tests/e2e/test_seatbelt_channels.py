"""TASK-0061 and decision-0010 item 3: a Seatbelt jail's channels on a Mac, against the real
`/usr/bin/sandbox-exec`. A channel the jail listens on is ready with its peer verified (the
listener's audit token and process group, read from the kernel); a listener the host put there
is refused; and no jail reaches another jail's channel, while the host does.
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from brig import (
    SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM,
    Channel,
    ChannelReady,
    ChannelRefused,
    Evidence,
    Jail,
    Reservations,
    at_most,
    await_channel_ready,
    create_seatbelt_jail,
    destroy_jail,
    grade,
    reserve_channels,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").exists(),
    reason="sandbox-exec is Darwin's; test skips on Linux, runs on a Mac",
)

_LISTEN = (
    "import socket, sys\n"
    "server = socket.socket(socket.AF_UNIX)\n"
    "server.bind(sys.argv[1])\n"
    "server.listen(8)\n"
    "held = []\n"
    "while True:\n"
    "    connection, _ = server.accept()\n"
    "    held.append(connection)\n"
)
"""Listen on the channel and hold every connection until its peer closes it (old SPEC
decision-210: darwin cannot read the peer of a connection its server already closed)."""

_DIAL = (
    "import errno, socket, sys\n"
    "try:\n"
    "    socket.socket(socket.AF_UNIX).connect(sys.argv[1])\n"
    "except OSError as error:\n"
    "    sys.exit(7 if error.errno in (errno.EPERM, errno.EACCES) else 3)\n"
)

_BIND = (
    "import errno, socket, sys\n"
    "try:\n"
    "    socket.socket(socket.AF_UNIX).bind(sys.argv[1])\n"
    "except OSError as error:\n"
    "    sys.exit(7 if error.errno in (errno.EPERM, errno.EACCES) else 3)\n"
)


def _listening_jail() -> tuple[Jail, Reservations]:
    reserved = reserve_channels((Channel("ctl"),))
    endpoint = reserved.reservations[0].endpoint
    jail = create_seatbelt_jail((sys.executable, "-I", "-c", _LISTEN, endpoint), channels=reserved)
    return jail, reserved


def test_a_channel_the_jail_listens_on_is_ready_with_a_verified_peer() -> None:
    jail, reserved = _listening_jail()
    try:
        outcome = await_channel_ready(jail, reserved.reservations[0], timeout_s=15)
        assert isinstance(outcome, ChannelReady), outcome
        outcome.connection.close()
    finally:
        destroy_jail(jail)


def test_a_listener_the_host_put_in_the_channel_directory_is_refused() -> None:
    """The host's listener is the embedder's own user, so only the process group tells it from
    the jail's: the check the audit token and `proc_pidinfo` make on Darwin."""
    reserved = reserve_channels((Channel("ctl"),))
    jail = create_seatbelt_jail(("/bin/sleep", "60"), channels=reserved)
    try:
        with socket.socket(socket.AF_UNIX) as impostor:
            impostor.bind(reserved.reservations[0].bound_path)
            impostor.listen(8)
            outcome = await_channel_ready(jail, reserved.reservations[0], timeout_s=5)
    finally:
        destroy_jail(jail)

    assert isinstance(outcome, ChannelRefused), outcome


def test_another_jail_cannot_reach_a_jail_s_channel() -> None:
    victim, reserved = _listening_jail()
    endpoint = reserved.reservations[0].endpoint
    try:
        ready = await_channel_ready(victim, reserved.reservations[0], timeout_s=15)
        assert isinstance(ready, ChannelReady), ready
        ready.connection.close()
        control = subprocess.run(
            (sys.executable, "-I", "-c", _DIAL, endpoint), check=False
        ).returncode
        attacker = create_seatbelt_jail((sys.executable, "-I", "-c", _DIAL, endpoint))
        try:
            attack = run_jail(attacker, timeout_s=15)
        finally:
            destroy_jail(attacker)
        squatter = create_seatbelt_jail(
            (sys.executable, "-I", "-c", _BIND, os.path.dirname(endpoint) + "/squat")
        )
        try:
            squat = run_jail(squatter, timeout_s=15)
        finally:
            destroy_jail(squatter)
    finally:
        destroy_jail(victim)

    assert control == 0, "control: the host dials the jail's channel"
    assert attack == 7
    assert squat == 7
    measured = grade(
        (SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM,),
        {
            SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM: Evidence(
                control_observed=control == 0, violation_blocked=attack == 7
            )
        },
    )
    claim = SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM
    assert at_most(attacker.report[claim], measured[claim])
