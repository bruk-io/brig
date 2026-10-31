"""TASK-0019: no jail can reach another jail's channels, measured against real bwrap.

Every jail's channel directory lives beneath brig's own state directory
(`presentation/api.py`'s `_allocate_channel_directory`), and so does every jail's
supervisor script. A Unix socket accepts a connect through a read-only mount and across
bwrap's network namespace (connect needs search on the path, not write), so whatever of
that directory a jail can see, it can dial. At a7e7f45 brig bound the whole of it into
every jail and jail B dialled jail A's reserved channel; this battery is that attempt,
planted.

Both jails run under the default policy, `WHOLE_HOST_READ_ONLY`, the hard case: the
policy itself binds the host root, state directory included, so only brig's own mask
over the state directory keeps the other jail's channels out. A policy that names
nothing under the state directory is the easy case, since brig's own binds were the only
way in; `tests/unit/test_bwrap_compile.py` pins that the compile names this jail's own
script and channel directory there and nothing wider.

Each jail's command sleeps rather than exits once it has written what it measured, for
the reason `test_channel_exclusivity_battery.py`'s `_JAILED_PROGRAM` gives: a command
that finishes takes its supervisor down before `create_bwrap_jail`'s namespace scan can
find it. What jail B measured comes back through a file in its own declared channel
directory, the one path the jail and the host legitimately share.

Uses brig's real state directory rather than a throwaway port: the property is about
what that directory exposes, so a battery that moved the channels elsewhere would not
measure it.
"""

import json
import shutil
import socket
import sys
import time
from pathlib import Path

import pytest

from brig import (
    Channel,
    ChannelReady,
    Jail,
    Reservations,
    await_channel_ready,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
)
from brig.infra.state_dir import ensure as _ensure_state_dir
from brig.infra.state_dir import resolve as _resolve_state_dir

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_ANSWER = b"jail-a-answers"
"""What jail A's listener sends every connection it accepts."""

_LISTENER = """
import socket, sys, time

listener = socket.socket(socket.AF_UNIX)
listener.bind(sys.argv[1])
listener.listen(8)
while True:
    connection, _ = listener.accept()
    try:
        connection.sendall(sys.argv[2].encode())
    except OSError:
        pass  # brig's own readiness check connects and leaves without reading
    connection.close()
"""
"""Jail A: answer every connection on its reserved endpoint, forever. It survives a
peer that leaves without reading (`await_channel_ready`'s verified connect does), so a
refused dial from jail B is never a dead listener.
"""

_DIALER = """
import json, os, socket, sys, time

target, state_dir, report = sys.argv[1:4]
outcome = {}
dialer = socket.socket(socket.AF_UNIX)
dialer.settimeout(5)
try:
    dialer.connect(target)
    outcome["dial"] = "connected:" + dialer.recv(64).decode(errors="replace")
except OSError as error:
    outcome["dial"] = type(error).__name__
try:
    outcome["state_dir"] = sorted(os.listdir(state_dir))
    outcome["channels"] = sorted(os.listdir(os.path.join(state_dir, "channels")))
except OSError as error:
    outcome["listing"] = type(error).__name__
with open(report + ".partial", "w") as handle:
    json.dump(outcome, handle)
os.rename(report + ".partial", report)
time.sleep(3600)
"""
"""Jail B: dial jail A's endpoint, list what it can see of the state directory, write
both into its own channel directory (renamed into place, so the host never reads half a
report), then sleep.
"""


def _endpoint(reservations: Reservations) -> str:
    """The one reservation's endpoint: each jail here declares exactly one channel."""
    (reservation,) = reservations.reservations
    return reservation.endpoint


def _jail_a() -> tuple[Jail, Reservations]:
    """Jail A, listening on its reserved channel, verified ready (asserted, so a channel
    that never comes up fails the test here rather than as a confusing dial result)."""
    reservations = reserve_channels((Channel("a"),))
    jail = create_bwrap_jail(
        (sys.executable, "-I", "-c", _LISTENER, _endpoint(reservations), _ANSWER.decode()),
        channels=reservations,
    )
    (reservation,) = reservations.reservations
    ready = await_channel_ready(jail, reservation, timeout_s=10)
    assert isinstance(ready, ChannelReady), ready
    return jail, reservations


def _wait_for(path: Path, *, timeout_s: float = 10.0) -> None:
    """Poll until `path` exists.

    Raises:
        TimeoutError: `path` never appeared before `timeout_s` passed.
    """
    deadline = time.monotonic() + timeout_s
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{path} never appeared")
        time.sleep(0.05)


def _dial_from_host(endpoint: str) -> bytes:
    """Dial `endpoint` from the host, outside any jail, and read the answer."""
    with socket.socket(socket.AF_UNIX) as dialer:
        dialer.settimeout(5)
        dialer.connect(endpoint)
        return dialer.recv(64)


def test_a_jail_cannot_dial_another_jails_channel_and_sees_only_its_own_state() -> None:
    """Jail B, given jail A's endpoint outright, cannot connect to it: the path does not
    exist in B's view of the state directory. Of that directory, B sees its own
    supervisor script and its own channel directory, nothing of A's.

    Positive control: the same endpoint answers from the host while B is running, so a
    refusal from B is the jail's doing, not a listener that is gone.
    """
    state_dir = str(_ensure_state_dir(_resolve_state_dir()))
    jail_a, reserved_a = _jail_a()
    try:
        reserved_b = reserve_channels((Channel("b"),))
        report = Path(reserved_b.directory.host_path) / "report.json"
        jail_b = create_bwrap_jail(
            (
                sys.executable,
                "-I",
                "-c",
                _DIALER,
                _endpoint(reserved_a),
                state_dir,
                str(report),
            ),
            channels=reserved_b,
        )
        try:
            _wait_for(report)
            outcome = json.loads(report.read_text())
            assert _dial_from_host(_endpoint(reserved_a)) == _ANSWER
        finally:
            destroy_jail(jail_b)
    finally:
        destroy_jail(jail_a)

    assert outcome["dial"] in {"FileNotFoundError", "ConnectionRefusedError"}, outcome
    assert jail_b.supervisor_script is not None
    assert outcome["state_dir"] == sorted(["channels", jail_b.supervisor_script.name])
    assert outcome["channels"] == [Path(reserved_b.directory.host_path).name]
