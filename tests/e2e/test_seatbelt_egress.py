"""TASK-0061, TASK-0063 and decision-0010 item 4: a Seatbelt jail's one route out, on a Mac,
against the real `/usr/bin/sandbox-exec` and brig's egress proxy. Each jail gets a bridge port of
its own, which the host listens on and hands its supervisor; the command reads it from its proxy
variables. The command reaches a granted destination only through that bridge; it cannot connect
around it, nor bind its own source port to the bridge's and connect anywhere (an outbound rule
filtered on the local port allowed that, TASK-0061), nor listen for a connection from off the host
(a bind rule allowed that, TASK-0063). Two jails with egress run at once. What stays open, and
keeps the grade best-effort, is pinned too: a host program that binds the jail's own port on
another local address.

A TLS-less HTTP server on the host's `127.0.0.1:<ephemeral>` stands in for the internet, granted
by its IP literal (decision-0009 item 4 refuses a name resolving to loopback).
"""

import errno
import http.server
import socket
import subprocess
import sys
import threading
import time
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

_BRIDGE_FROM_ENV = r"""
import os
BRIDGE = int(os.environ["HTTP_PROXY"].rsplit(":", 1)[1])
"""
"""Every jailed client starts with this: its own bridge port, from the proxy variable brig sets
to it (decision-0009 item 7), the one TCP port its profile lets it reach."""


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


_THROUGH_BRIDGE = (
    _BRIDGE_FROM_ENV
    + r"""
import socket, sys, time
port = int(sys.argv[1])
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 0)
sock = socket.create_connection(("127.0.0.1", BRIDGE), timeout=10)
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
)

_AROUND_BRIDGE = r"""
import errno, socket, sys
try:
    socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=5).close()
except OSError as error:
    sys.exit(7 if error.errno in (errno.EPERM, errno.EACCES) else 3)
"""

_OFF_HOST = ("1.1.1.1", "80")
"""An address off this host: what the bypass first measured reached (TASK-0061)."""

_FROM_BRIDGE_PORT = (
    _BRIDGE_FROM_ENV.replace('os.environ["HTTP_PROXY"]', 'os.environ.get("HTTP_PROXY", "x:0")')
    + r"""
import socket, sys
source = BRIDGE if sys.argv[3] == "bridge" else int(sys.argv[3])
sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(("0.0.0.0", source))
    sock.settimeout(5)
    sock.connect((sys.argv[1], int(sys.argv[2])))
except OSError as error:
    print(f"refused: errno {error.errno} ({error.strerror})", flush=True)
    sys.exit(1)
print(f"connected from {sock.getsockname()}", flush=True)
"""
)
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
    target = (*_OFF_HOST, "bridge")
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


def _jail(program: str, *argv: str, granted: int, out: Path) -> Jail:
    return create_seatbelt_jail(
        (sys.executable, "-I", "-c", program, *argv),
        egress=EgressPolicy(allow=(Destination("127.0.0.1", granted),)),
        stdio=Stdio(stdout=str(out), stderr=str(out)),
    )


def test_two_jails_with_egress_run_at_once(server_port: int, tmp_path: Path) -> None:
    """bh-02 starts two jails with egress; with one fixed bridge port on the host's one stack,
    the second's supervisor could not bind it and never started its command (TASK-0063)."""
    first = _jail(_THROUGH_BRIDGE, str(server_port), "1", granted=server_port, out=tmp_path / "a")
    try:
        second = _jail(
            _THROUGH_BRIDGE, str(server_port), "1", granted=server_port, out=tmp_path / "b"
        )
        try:
            results = (run_jail(first, timeout_s=30), run_jail(second, timeout_s=30))
        finally:
            destroy_jail(second)
    finally:
        destroy_jail(first)

    assert results == (0, 0), (
        (tmp_path / "a").read_text() if (tmp_path / "a").exists() else "",
        (tmp_path / "b").read_text() if (tmp_path / "b").exists() else "",
    )


_LISTEN = (
    _BRIDGE_FROM_ENV
    + r"""
import socket, sys
attempts = [
    (("0.0.0.0", BRIDGE), ("SO_REUSEADDR",)),
    (("0.0.0.0", BRIDGE), ("SO_REUSEADDR", "SO_REUSEPORT")),
    ((sys.argv[1], BRIDGE), ("SO_REUSEADDR",)),
    (("0.0.0.0", 0), ()),
]
listening = []
for address, options in attempts:
    sock = socket.socket()
    for option in options:
        sock.setsockopt(socket.SOL_SOCKET, getattr(socket, option), 1)
    try:
        sock.bind(address)
        sock.listen(1)
    except OSError as error:
        print(f"refused {address} {options}: errno {error.errno}", flush=True)
        continue
    listening.append(f"{address} {options}")
print("listening:", listening, flush=True)
sys.exit(0 if listening else 7)
"""
)
"""Try to listen where a machine off the host could connect: the wildcard address at the jail's
own bridge port (with each reuse option), the host's LAN address there, and any port. Exits 0 if
any listen succeeded, 7 if all were refused, and prints each errno."""


def _lan_address() -> str | None:
    """This host's address towards the internet (no packet is sent), or `None` with no route."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("1.1.1.1", 80))
        except OSError:
            return None
        address = str(probe.getsockname()[0])
    return None if address.startswith("127.") else address


def test_a_jailed_command_cannot_listen_for_a_connection_from_off_the_host(
    server_port: int, tmp_path: Path
) -> None:
    lan = _lan_address() or "0.0.0.0"
    control = subprocess.run(
        (sys.executable, "-I", "-c", _LISTEN, lan),
        env={"HTTP_PROXY": "http://127.0.0.1:0"},
        capture_output=True,
        text=True,
        check=False,
    )
    out = tmp_path / "out"
    jail = _jail(_LISTEN, lan, granted=server_port, out=out)
    try:
        attack = run_jail(jail, timeout_s=30)
    finally:
        destroy_jail(jail)

    said = out.read_text()
    assert control.returncode == 0, f"control: unjailed, a listen succeeds: {control.stdout}"
    assert attack == 7, f"a jailed command listened where the LAN can reach it: {said}"
    refusals = [line for line in said.splitlines() if line.startswith("refused")]
    assert len(refusals) == 4, said
    assert all(line.endswith(f"errno {errno.EPERM}") for line in refusals), said


_CUED = (
    _BRIDGE_FROM_ENV
    + r"""
import errno, os, socket, sys, time
print(BRIDGE, flush=True)
cue = sys.argv[2]
while not os.path.exists(cue):
    time.sleep(0.02)
try:
    socket.create_connection((sys.argv[1], BRIDGE), timeout=5).close()
except OSError as error:
    print(f"refused: errno {error.errno}", flush=True)
    sys.exit(7 if error.errno in (errno.EPERM, errno.EACCES) else 3)
print("reached", flush=True)
"""
)
"""Print the jail's bridge port, wait for the host's cue, then connect to that port at the host's
LAN address. Exits 0 if it connected."""


def _squat(family: socket.AddressFamily, address: tuple[object, ...], option: str | None) -> str:
    """Bind `address` the way a host program would, with `option` (an address-reuse option) or
    none, and say what happened: `bound` or the errno."""
    squatter = socket.socket(family)
    try:
        if family == socket.AF_INET6:
            squatter.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        if option is not None:
            squatter.setsockopt(socket.SOL_SOCKET, getattr(socket, option), 1)
        squatter.bind(address)
    except OSError as error:
        return f"errno {error.errno}"
    finally:
        squatter.close()
    return "bound"


_SQUATS: tuple[tuple[str, str | None], ...] = (
    ("lan", None),
    ("lan", "SO_REUSEADDR"),
    ("lan", "SO_REUSEPORT"),
    ("link-local", None),
    ("link-local", "SO_REUSEADDR"),
)
"""Each squatter: at the LAN address or at `fe80::1%lo0`, plainly or with a reuse option."""


def _squat_all(lan: str, port: int) -> dict[tuple[str, str | None], str]:
    lo0 = socket.if_nametoindex("lo0")
    places: dict[str, tuple[socket.AddressFamily, tuple[object, ...]]] = {
        "lan": (socket.AF_INET, (lan, port)),
        "link-local": (socket.AF_INET6, ("fe80::1", port, 0, lo0)),
    }
    return {(place, option): _squat(*places[place], option) for place, option in _SQUATS}


def test_a_host_program_cannot_take_the_jails_port_at_another_local_address(
    server_port: int, tmp_path: Path
) -> None:
    """DRAFT-0036: Seatbelt's `localhost` matches every local address, so a host program bound
    at the jail's port on the LAN or a link-local address would be reached past the proxy. The
    host holds the port, bound and not listening, at every local address present at create, so
    each squatter fails `EADDRINUSE`, reuse option or not; a wildcard squatter with a reuse
    option can bind, and a connect to the LAN address at the port still does not reach it.
    Control: holding only the two loopback listeners, as before, every squatter binds."""
    lan = _lan_address()
    if lan is None:
        pytest.skip("this host has no address off loopback to measure against")
    v4 = socket.create_server(("127.0.0.1", 0))
    control_port = v4.getsockname()[1]
    loopbacks = (v4, socket.create_server(("::1", control_port), family=socket.AF_INET6))
    try:
        control = _squat_all(lan, control_port)
    finally:
        for listener in loopbacks:
            listener.close()
    out = tmp_path / "out"
    cue = tmp_path / "cue"
    jail = _jail(_CUED, lan, str(cue), granted=server_port, out=out)
    try:
        deadline = time.monotonic() + 10
        while not (out.exists() and out.read_text().strip()):
            assert time.monotonic() < deadline, "the jail never printed its port"
            time.sleep(0.02)
        port = int(out.read_text().split()[0])
        attack = _squat_all(lan, port)
        wildcard = socket.socket()
        wildcard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        wildcard.bind(("0.0.0.0", port))
        wildcard.listen(1)
        wildcard.settimeout(3)
        cue.write_text("")
        try:
            dialled = run_jail(jail, timeout_s=30)
            try:
                wildcard.accept()[0].close()
                reached = True
            except TimeoutError:
                reached = False
        finally:
            wildcard.close()
    finally:
        destroy_jail(jail)

    assert all(result == "bound" for result in control.values()), control
    assert all(result == f"errno {errno.EADDRINUSE}" for result in attack.values()), attack
    assert dialled != 0 and not reached, out.read_text()
    assert jail.report[SEATBELT_NETWORK_EGRESS_CLAIM].name == "BEST_EFFORT"


_OPEN_FDS = r"""
import os, sys
held = []
for fd in range(3, 256):
    try:
        os.fstat(fd)
    except OSError:
        continue
    held.append(fd)
print("held:", held, flush=True)
sys.exit(0 if not held else 9)
"""
"""List every fd above stdio the command holds: the bridge's listeners, passed to its supervisor,
must not be among them, or the command could accept on its own bridge port."""


def test_the_command_holds_none_of_the_bridge_s_listeners(server_port: int, tmp_path: Path) -> None:
    out = tmp_path / "out"
    jail = _jail(_OPEN_FDS, granted=server_port, out=out)
    try:
        held = run_jail(jail, timeout_s=30)
    finally:
        destroy_jail(jail)

    assert held == 0, out.read_text()
