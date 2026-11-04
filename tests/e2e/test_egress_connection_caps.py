"""TASK-0049: the egress route holds at most a stated number of connections at once, in the proxy
and in the supervisor's bridge, against real bwrap.

The stand-in for the internet is the route batteries': a TLS-less HTTP server on the host's
`127.0.0.1:<ephemeral>`, reached as `granted.test` through the proxy's resolver seam, with the
literal granted so a name resolving to it may reach it (decision-0009 item 4). Each cap is
lowered to `_CAP` (`EgressLimits`), the other left at its default, so the cap under test is the
one that refuses.

One command runs in the jail for the whole journey and acts on cue files the host writes,
printing one JSON line per step: it holds `_CAP` tunnels open (step 1), tries one HTTP and one
SOCKS5 connection more (step 2), then closes one tunnel and opens another (step 3). Before step
1, after it and after step 2, the host counts the proxy's threads and fds, and the command
counts its PID 1's threads (the bridge's).
"""

import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
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

_CAP = 3
"""The cap each test lowers its limit to."""

_STEP_TIMEOUT_S = 30.0

_CAPPED_BODY = "brig: egress refused: the jail holds as many connections as it may"

_CLIENT = r"""
import json, os, socket, sys, time

port, cues, cap = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
bridge = ("127.0.0.1", 3128)


def wait(step):
    while not os.path.exists(os.path.join(cues, str(step))):
        time.sleep(0.02)


def say(step, **seen):
    print(json.dumps({"step": step, "bridge_threads": len(os.listdir("/proc/1/task")), **seen}),
          flush=True)


def read_all(sock):
    data = b""
    try:
        while chunk := sock.recv(65536):
            data += chunk
    except OSError as error:
        return data.decode() or type(error).__name__
    return data.decode()


def tunnel():
    sock = socket.create_connection(bridge, timeout=10)
    head = b""
    try:
        sock.sendall(f"CONNECT granted.test:{port} HTTP/1.1\r\n\r\n".encode())
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(1)
            if not chunk:
                break
            head += chunk
    except OSError as error:
        sock.close()
        return None, head.decode() or type(error).__name__
    if head.startswith(b"HTTP/1.1 200"):
        return sock, head.decode().split("\r\n")[0]
    return None, (head + read_all(sock).encode()).decode()


def socks():
    sock = socket.create_connection(bridge, timeout=10)
    try:
        sock.sendall(b"\x05\x01\x00")
        if sock.recv(2) != b"\x05\x00":
            return "closed"
        raw = b"granted.test"
        sock.sendall(b"\x05\x01\x00\x03" + bytes([len(raw)]) + raw + port.to_bytes(2, "big"))
        reply = sock.recv(10)
        return f"reply {reply[1]:#04x}" if len(reply) > 1 else "closed"
    except OSError as error:
        return type(error).__name__
    finally:
        sock.close()


wait(1)
held = [tunnel() for _ in range(cap)]
say(1, heads=[head for _, head in held])

wait(2)
_, extra = tunnel()
say(2, http=extra, socks=socks())

wait(3)
held[0][0].close()
deadline, head = time.monotonic() + 10, ""
while time.monotonic() < deadline:
    sock, head = tunnel()
    if sock is not None:
        sock.close()
        break
    time.sleep(0.05)
say(3, head=head)
for sock, _ in held[1:]:
    sock.close()
"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture(scope="module")
def server() -> Iterator[int]:
    """The stand-in for the internet: an HTTP server on the host's loopback; its port."""
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()


@dataclass(frozen=True)
class _Count:
    """The proxy's threads and open fds, counted on the host at one moment."""

    threads: int
    fds: int


@dataclass(frozen=True)
class _Journey:
    """What one journey saw: each step's line, and the proxy's count before step 1 (`idle`),
    after it (`held`), and after step 2 (`refused`)."""

    steps: tuple[dict[str, object], ...]
    idle: _Count
    held: _Count
    refused: _Count


def _proxy_children() -> list[int]:
    """The egress proxies that are this process's children now, by their cmdline."""
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            stat = Path(f"/proc/{name}/stat").read_text()
            cmdline = Path(f"/proc/{name}/cmdline").read_bytes()
        except OSError:
            continue
        parent = int(stat.rpartition(")")[2].split()[1])
        if parent == os.getpid() and cmdline == f"{sys.executable}\0-I\0-\0".encode():
            found.append(int(name))
    return found


def _count(pid: int) -> _Count:
    return _Count(
        threads=len(os.listdir(f"/proc/{pid}/task")), fds=len(os.listdir(f"/proc/{pid}/fd"))
    )


def _step(cues: Path, out: Path, step: int) -> dict[str, object]:
    """Cue `step`, and wait for the line the command prints for it.

    Raises:
        AssertionError: the command printed nothing for `step` within `_STEP_TIMEOUT_S`.
    """
    (cues / str(step)).write_text("")
    deadline = time.monotonic() + _STEP_TIMEOUT_S
    while time.monotonic() < deadline:
        lines = out.read_text().splitlines() if out.exists() else []
        if len(lines) >= step:
            seen = json.loads(lines[step - 1])
            assert isinstance(seen, dict)
            assert seen["step"] == step
            return seen
        time.sleep(0.02)
    raise AssertionError(f"the command printed nothing for step {step}")


def _journey(server: int, limits: EgressLimits) -> _Journey:
    with tempfile.TemporaryDirectory(dir="/tmp") as scratch:
        out, cues = Path(scratch) / "out", Path(scratch) / "cues"
        cues.mkdir()
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _CLIENT, str(server), str(cues), str(_CAP)),
            egress=EgressPolicy(
                (Destination("granted.test", server), Destination("127.0.0.1", server))
            ),
            egress_hosts={"granted.test": ("127.0.0.1",)},
            egress_limits=limits,
            stdio=Stdio(stdout=str(out)),
        )
        try:
            [proxy] = _proxy_children()
            idle = _count(proxy)
            first = _step(cues, out, 1)
            held = _count(proxy)
            second = _step(cues, out, 2)
            refused = _count(proxy)
            third = _step(cues, out, 3)
            assert run_jail(jail, timeout_s=_STEP_TIMEOUT_S) == 0
        finally:
            destroy_jail(jail)
    return _Journey((first, second, third), idle, held, refused)


def test_the_proxy_serves_at_most_its_cap_and_refuses_one_more_with_403_or_socks_0x01(
    server: int,
) -> None:
    """With the proxy's cap lowered and the bridge's not, `_CAP` tunnels are served and one more
    is refused in its own protocol and closed. The proxy's count: each tunnel holds two threads
    and two fds (the jail's end and the upstream connection), and the refused ones leave none.
    Closing a tunnel frees its slot: the cap is on connections at once, not in all."""
    journey = _journey(server, EgressLimits(connections=_CAP))
    first, second, third = journey.steps

    assert first["heads"] == ["HTTP/1.1 200 Connection established"] * _CAP
    assert isinstance(second["http"], str)
    assert second["http"].startswith("HTTP/1.1 403 Forbidden")
    assert second["http"].endswith(f"\r\n\r\n{_CAPPED_BODY}")
    assert second["socks"] == "reply 0x01"
    assert third["head"] == "HTTP/1.1 200 Connection established"
    assert journey.held.threads == journey.idle.threads + 2 * _CAP
    assert journey.held.fds == journey.idle.fds + 2 * _CAP
    assert journey.refused == journey.held


def test_the_bridge_relays_at_most_its_cap_and_closes_one_more_unanswered(server: int) -> None:
    """With the bridge's cap lowered and the proxy's not, `_CAP` tunnels are relayed and one
    more is closed by the bridge with no answer at all: it never reaches the proxy, whose count
    does not move. The bridge's own count (PID 1's threads, read in the jail): two per tunnel,
    and none for the closed ones. Closing a tunnel frees its slot."""
    journey = _journey(server, EgressLimits(bridge_connections=_CAP))
    first, second, third = journey.steps

    assert first["heads"] == ["HTTP/1.1 200 Connection established"] * _CAP
    assert second["http"] in ("", "ConnectionResetError")
    assert second["socks"] in ("closed", "ConnectionResetError", "BrokenPipeError")
    assert second["bridge_threads"] == first["bridge_threads"]
    assert third["head"] == "HTTP/1.1 200 Connection established"
    assert journey.held.threads == journey.idle.threads + 2 * _CAP
    assert journey.refused == journey.held


_HOLDER = r"""
import socket, sys, time

port, cap = int(sys.argv[1]), int(sys.argv[2])
held = []
for _ in range(cap):
    sock = socket.create_connection(("127.0.0.1", 3128), timeout=10)
    sock.sendall(f"CONNECT granted.test:{port} HTTP/1.1\r\n\r\n".encode())
    held.append(sock)
for sock in held:
    sock.recv(64)
print("held", flush=True)
time.sleep(60)
"""


def test_destroy_jail_at_the_cap_leaves_no_proxy_process_thread_or_fd(server: int) -> None:
    """Law 7 with the route full: a jail holding as many tunnels as its proxy serves is
    destroyed, and no proxy, thread or fd of it is left on the host."""
    threads, fds = set(threading.enumerate()), set(os.listdir("/proc/self/fd"))

    with tempfile.TemporaryDirectory(dir="/tmp") as scratch:
        out = Path(scratch) / "out"
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _HOLDER, str(server), str(_CAP)),
            egress=EgressPolicy(
                (Destination("granted.test", server), Destination("127.0.0.1", server))
            ),
            egress_hosts={"granted.test": ("127.0.0.1",)},
            egress_limits=EgressLimits(connections=_CAP),
            stdio=Stdio(stdout=str(out)),
        )
        try:
            deadline = time.monotonic() + _STEP_TIMEOUT_S
            while time.monotonic() < deadline and not (out.exists() and out.read_text()):
                time.sleep(0.02)
            [proxy] = _proxy_children()
            full = _count(proxy)
        finally:
            destroy_jail(jail)
        held = out.read_text()

    assert full.threads > 2 * _CAP
    assert held == "held\n"
    assert _proxy_children() == []
    with pytest.raises(ChildProcessError):
        os.waitid(os.P_PID, proxy, os.WEXITED | os.WNOHANG)
    assert set(threading.enumerate()) <= threads
    assert set(os.listdir("/proc/self/fd")) == fds
