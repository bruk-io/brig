"""TASK-0049's repro: a handshake's limit is a total, not a per-read one, against real bwrap.

A client in the jail opens a connection to the bridge and sends an HTTP request head one byte a
second, never finishing it, so it never names its destination. With the handshake limit lowered
to `_LIMIT_S`, the proxy must close it once that much time has passed in all, whatever pace the
bytes keep. A per-read timeout never fires on it: each read waits a second.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from brig import (
    Destination,
    EgressLimits,
    EgressPolicy,
    Stdio,
    create_bwrap_jail,
    destroy_jail,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_LIMIT_S = 2.0
"""The handshake limit the test lowers the proxy's to."""

_HORIZON_S = 8
"""How many seconds the client keeps sending, one byte each: four times the limit."""

_CLIENT = r"""
import json, select, socket, sys, time

horizon = int(sys.argv[1])
head = b"CONNECT granted.test:80 HTTP/1.1\r\nX-Slow: " + b"a" * horizon
sock = socket.create_connection(("127.0.0.1", 3128), timeout=10)
start = time.monotonic()
closed_after = None
for byte in head[:horizon]:
    try:
        sock.sendall(bytes([byte]))
        ready, _, _ = select.select([sock], [], [], 1.0)
        if ready and not sock.recv(1):
            closed_after = time.monotonic() - start
            break
    except OSError:
        closed_after = time.monotonic() - start
        break
print(json.dumps({"closed_after": closed_after}))
"""


def test_a_client_sending_one_header_byte_a_second_is_closed_past_the_total_limit() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as streams:
        out = Path(streams) / "out.json"
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _CLIENT, str(_HORIZON_S)),
            egress=EgressPolicy((Destination("granted.test", 80),)),
            egress_limits=EgressLimits(handshake_s=_LIMIT_S),
            stdio=Stdio(stdout=str(out)),
        )
        try:
            assert run_jail(jail, timeout_s=60) == 0
        finally:
            destroy_jail(jail)
        seen = json.loads(out.read_text())

    closed_after = seen["closed_after"]
    assert closed_after is not None, "the slow handshake was still open past the total limit"
    assert _LIMIT_S <= closed_after < _LIMIT_S + 2
