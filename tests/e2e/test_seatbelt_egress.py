"""TASK-0061 and decision-0010 item 4: a Seatbelt jail's one route out, on a Mac, against the real
`/usr/bin/sandbox-exec` and brig's egress proxy. The command reaches a granted destination only
through the supervisor's bridge; it cannot connect around it, nor bind its own source port to the
bridge's and connect anywhere, which an outbound rule filtered on the local port allowed
(measured, TASK-0061).

A TLS-less HTTP server on the host's `127.0.0.1:<ephemeral>` stands in for the internet, granted
by its IP literal (decision-0009 item 4 refuses a name resolving to loopback).
"""

import errno
import http.server
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from brig import (
    SEATBELT_NETWORK_EGRESS_CLAIM,
    Destination,
    EgressPolicy,
    Evidence,
    Jail,
    Stdio,
    at_most,
    create_seatbelt_jail,
    destroy_jail,
    grade,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").exists(),
    reason="sandbox-exec is Darwin's; test skips on Linux, runs on a Mac",
)

_BODY = b"hello from the test server"

_BRIDGE_PORT = 3128
"""The supervisor's bridge port, the one TCP port the profile lets the command reach."""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", str(len(_BODY)))
        self.end_headers()
        self.wfile.write(_BODY)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture
def server_port() -> Iterator[int]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


_THROUGH_BRIDGE = r"""
import socket, sys
port = int(sys.argv[1])
sock = socket.create_connection(("127.0.0.1", 3128), timeout=10)
sock.sendall(f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode())
head = b""
while b"\r\n\r\n" not in head:
    chunk = sock.recv(1)
    if not chunk:
        sys.exit(3)
    head += chunk
if not head.startswith(b"HTTP/1.1 200"):
    sys.exit(4)
sock.sendall(b"GET / HTTP/1.0\r\n\r\n")
data = b""
while chunk := sock.recv(65536):
    data += chunk
sys.exit(0 if b"hello from the test server" in data else 5)
"""

_AROUND_BRIDGE = r"""
import errno, socket, sys
try:
    socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=5).close()
except OSError as error:
    sys.exit(7 if error.errno in (errno.EPERM, errno.EACCES) else 3)
"""

_OFF_HOST = ("1.1.1.1", "80")
"""An address off this host: what the bypass first measured reached (TASK-0061)."""

_FROM_BRIDGE_PORT = r"""
import socket, sys
sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(("0.0.0.0", int(sys.argv[3])))
    sock.settimeout(5)
    sock.connect((sys.argv[1], int(sys.argv[2])))
except OSError as error:
    print(f"refused: errno {error.errno} ({error.strerror})", flush=True)
    sys.exit(1)
print(f"connected from {sock.getsockname()}", flush=True)
"""
"""Bind the source port to the bridge's, on the wildcard address beside the supervisor's own
loopback listener, and connect off the host. Exits 0 only when the connect succeeded, and says
why when it did not."""


def _egress_jail_exit(program: str, *argv: str, granted: int) -> tuple[int, Jail]:
    jail = create_seatbelt_jail(
        (sys.executable, "-I", "-c", program, *argv),
        egress=EgressPolicy(allow=(Destination("127.0.0.1", granted),)),
        stdio=Stdio(stdout="/dev/null", stderr="/dev/null"),
    )
    try:
        return run_jail(jail, timeout_s=30), jail
    finally:
        destroy_jail(jail)


def test_a_granted_destination_is_reached_only_through_the_bridge(server_port: int) -> None:
    port = str(server_port)
    control = subprocess.run(
        (sys.executable, "-I", "-c", _AROUND_BRIDGE, port), check=False
    ).returncode
    through, _ = _egress_jail_exit(_THROUGH_BRIDGE, port, granted=server_port)
    around, jail = _egress_jail_exit(_AROUND_BRIDGE, port, granted=server_port)

    assert control == 0, "control: the host reaches the server directly"
    assert through == 0
    assert around == 7
    claim = SEATBELT_NETWORK_EGRESS_CLAIM
    measured = grade(
        (claim,), {claim: Evidence(control_observed=through == 0, violation_blocked=around == 7)}
    )
    assert at_most(jail.report[claim], measured[claim])


def test_a_source_port_bound_to_the_bridge_s_does_not_open_a_route(
    server_port: int, tmp_path: Path
) -> None:
    """Fails if the jailed connect succeeds; any refusal passes, and its errno is shown. The
    control connects from an ephemeral port: from the bridge's own, its closed connection's
    TIME_WAIT would hold the very address pair the attack uses, which then fails `EADDRINUSE`
    whatever the profile says, a probe that measured nothing (so that errno fails too)."""
    target = (*_OFF_HOST, str(_BRIDGE_PORT))
    control = subprocess.run(
        (sys.executable, "-I", "-c", _FROM_BRIDGE_PORT, *_OFF_HOST, "0"),
        check=False,
        capture_output=True,
        text=True,
    )
    if control.returncode != 0:
        pytest.skip(f"no route off this host to measure against: {control.stdout.strip()}")
    out = tmp_path / "out"
    jail = create_seatbelt_jail(
        (sys.executable, "-I", "-c", _FROM_BRIDGE_PORT, *target),
        egress=EgressPolicy(allow=(Destination("127.0.0.1", server_port),)),
        stdio=Stdio(stdout=str(out), stderr="/dev/null"),
    )
    try:
        attack = run_jail(jail, timeout_s=30)
    finally:
        destroy_jail(jail)

    said = out.read_text().strip() if out.exists() else "(nothing)"
    assert attack != 0, f"a jailed socket bound to the bridge's port reached {_OFF_HOST}: {said}"
    assert f"errno {errno.EADDRINUSE} " not in said, f"inconclusive, nothing measured: {said}"
    print(f"jailed attempt: exit {attack}, {said}")


def test_an_ungranted_destination_is_refused_by_the_proxy(server_port: int) -> None:
    with socket.create_server(("127.0.0.1", 0)) as other:
        ungranted = other.getsockname()[1]
        result, _ = _egress_jail_exit(_THROUGH_BRIDGE, str(ungranted), granted=server_port)

    assert result == 4, "the proxy answers the CONNECT with a refusal, not a 200"
