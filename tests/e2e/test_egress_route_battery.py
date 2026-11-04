"""TASK-0001.36: a jail's one route out (decision-0009 items 1, 2 and 7), against real bwrap.

A TLS-less HTTP server on the host's `127.0.0.1:<ephemeral>` stands in for the internet. The test
names reach it through the proxy's resolver seam, `create_bwrap_jail(egress_hosts=...)`: a table
the proxy resolves names from instead of the host's resolver, so no DNS is used. The address is
loopback, which decision-0009 item 4 refuses to a name unless an IP-literal grant names it, so the
granted name's tests also grant `127.0.0.1:<port>`; the test without that literal is the refusal
of a name resolving to 127.0.0.1.

Each command is a Python client run in the jail that prints one JSON object of what it saw.
"""

import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from brig import (
    Destination,
    EgressPolicy,
    JailSpawnFailed,
    Stdio,
    create_bwrap_jail,
    destroy_jail,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_BODY = b"hello from the test server"

_PROXY_ARGV = (sys.executable, "-I", "-")
"""How the egress proxy is run: its cmdline, which is how this battery finds it on the host."""

_CLIENT = r"""
import json, os, socket, sys, urllib.request

port = int(sys.argv[1])
bridge = ("127.0.0.1", 3128)
seen = {"env": {k: v for k, v in os.environ.items() if "proxy" in k.lower()}}


def read_all(sock):
    data = b""
    while chunk := sock.recv(65536):
        data += chunk
    return data


def connect(name):
    sock = socket.create_connection(bridge, timeout=10)
    sock.sendall(f"CONNECT {name}:{port} HTTP/1.1\r\nHost: {name}:{port}\r\n\r\n".encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = sock.recv(1)
        if not chunk:
            break
        head += chunk
    if not head.startswith(b"HTTP/1.1 200"):
        return (head + read_all(sock)).decode()
    sock.sendall(b"GET / HTTP/1.0\r\n\r\n")
    return read_all(sock).decode()


def socks(name):
    sock = socket.create_connection(bridge, timeout=10)
    sock.sendall(b"\x05\x01\x00")
    if sock.recv(2) != b"\x05\x00":
        return "no method"
    raw = name.encode()
    sock.sendall(b"\x05\x01\x00\x03" + bytes([len(raw)]) + raw + port.to_bytes(2, "big"))
    reply = sock.recv(10)
    if reply[1] != 0:
        return f"reply {reply[1]:#04x}"
    sock.sendall(b"GET / HTTP/1.0\r\n\r\n")
    return read_all(sock).decode()


def attempt(fn, *args):
    try:
        return fn(*args)
    except Exception as error:
        return f"{type(error).__name__}: {error}"


for name in sys.argv[2:]:
    seen[f"connect {name}"] = attempt(connect, name)
    seen[f"socks {name}"] = attempt(socks, name)
    seen[f"urllib {name}"] = attempt(
        lambda: urllib.request.urlopen(f"http://{name}:{port}/", timeout=10).read().decode()
    )

def dial(host, to):
    socket.create_connection((host, to), timeout=3)
    return "reached"


seen["direct"] = attempt(dial, "127.0.0.1", port)
seen["off host"] = attempt(dial, "192.0.2.1", 80)
seen["resolver"] = attempt(lambda: socket.getaddrinfo("granted.test", port) and "resolved")
seen["fd 5"] = attempt(lambda: os.fstat(5) and "open")
seen["pid 1 fd 5"] = attempt(lambda: os.open("/proc/1/fd/5", os.O_RDWR) and "opened")
seen["proxy named"] = [
    pid
    for pid in os.listdir("/proc")
    if pid.isdigit() and b"-I\x00-\x00" in open(f"/proc/{pid}/cmdline", "rb").read()
]
print(json.dumps(seen))
"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", str(len(_BODY)))
        self.end_headers()
        self.wfile.write(_BODY)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture
def server() -> Iterator[int]:
    """The stand-in for the internet: an HTTP server on the host's loopback; its port."""
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()


def _run(port: int, egress: EgressPolicy | None, *names: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(dir="/tmp") as streams:
        out = Path(streams) / "out.json"
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _CLIENT, str(port), *names),
            egress=egress,
            egress_hosts={"granted.test": ("127.0.0.1",), "local.test": ("127.0.0.1",)},
            stdio=Stdio(stdout=str(out)),
        )
        try:
            assert run_jail(jail, timeout_s=60) == 0
        finally:
            destroy_jail(jail)
        seen = json.loads(out.read_text())
    assert isinstance(seen, dict)
    return seen


def _granting(port: int, *hosts: str) -> EgressPolicy:
    return EgressPolicy(tuple(Destination(host, port) for host in hosts))


def _proxies() -> list[int]:
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
        if parent == os.getpid() and tuple(cmdline.decode().split("\0")[:-1]) == _PROXY_ARGV:
            found.append(int(name))
    return found


def test_a_granted_name_is_reached_over_connect_socks5_and_the_environments_proxy(
    server: int,
) -> None:
    seen = _run(server, _granting(server, "granted.test", "127.0.0.1"), "granted.test")

    for way in ("connect", "socks"):
        reply = seen[f"{way} granted.test"]
        assert isinstance(reply, str)
        assert reply.startswith("HTTP/1.0 200")
        assert reply.endswith(_BODY.decode())
    assert seen["urllib granted.test"] == _BODY.decode()


def test_an_ungranted_name_is_refused_with_the_403_signature_and_socks_0x02(
    server: int,
) -> None:
    seen = _run(server, _granting(server, "granted.test", "127.0.0.1"), "elsewhere.test")

    reply = seen["connect elsewhere.test"]
    assert isinstance(reply, str)
    assert reply.startswith("HTTP/1.1 403 Forbidden")
    assert reply.endswith(f"\r\n\r\nbrig: egress denied by policy: elsewhere.test:{server}")
    assert seen["socks elsewhere.test"] == "reply 0x02"


def test_a_name_resolving_to_loopback_is_refused_without_an_ip_grant(server: int) -> None:
    """decision-0009 item 4: `local.test` is granted by name and resolves to 127.0.0.1, which no
    IP-literal grant names, so it reaches nothing; the positive control is the first test, where
    the literal is granted too."""
    seen = _run(server, _granting(server, "local.test"), "local.test")

    reply = seen["connect local.test"]
    assert isinstance(reply, str)
    assert reply.endswith(f"\r\n\r\nbrig: egress denied by policy: local.test:{server}")
    assert seen["socks local.test"] == "reply 0x02"


def test_a_program_that_ignores_the_proxy_settings_reaches_nothing(server: int) -> None:
    """The jail keeps its own network namespace: the server's address is the jail's own
    loopback there, an off-host address has no route, and there is no resolver. The positive
    control is the same server reached through the proxy in the first test."""
    seen = _run(server, _granting(server, "granted.test", "127.0.0.1"))

    assert str(seen["direct"]).startswith("ConnectionRefusedError")
    assert str(seen["off host"]).startswith("OSError")
    assert str(seen["resolver"]).startswith("gaierror")


def test_nothing_in_the_jail_names_or_holds_the_proxy(server: int) -> None:
    """The jail's environment names only its own loopback, and its procfs shows no proxy (the
    proxy runs from its stdin, so no file names it either). The positive control: the same
    cmdline scan on the host finds it while the jail runs (`test_destroy_jail_leaves_...`). The
    command holds no fd 5, the supervisor's end towards the proxy, and cannot reopen it through
    `/proc/1/fd` (decision-0006: PID 1 is non-dumpable)."""
    seen = _run(server, _granting(server, "granted.test", "127.0.0.1"))

    env = seen["env"]
    assert isinstance(env, dict)
    assert set(env.values()) == {"http://127.0.0.1:3128", "socks5h://127.0.0.1:3128", ""}
    assert seen["proxy named"] == []
    assert str(seen["fd 5"]).startswith("OSError: [Errno 9]")
    assert str(seen["pid 1 fd 5"]).startswith("PermissionError")


def test_without_an_egress_policy_nothing_listens_and_nothing_is_set(server: int) -> None:
    seen = _run(server, None, "granted.test")

    assert seen["env"] == {}
    assert str(seen["connect granted.test"]).startswith("ConnectionRefusedError")
    assert _proxies() == []


def _fds() -> set[str]:
    return set(os.listdir("/proc/self/fd"))


def test_destroy_jail_leaves_no_proxy_process_thread_or_fd(server: int) -> None:
    threads, fds = set(threading.enumerate()), _fds()

    jail = create_bwrap_jail(
        ("sleep", "30"), egress=_granting(server, "granted.test"), stdio=Stdio(stdout="/dev/null")
    )
    running = _proxies()
    destroy_jail(jail)

    assert len(running) == 1
    assert _proxies() == []
    with pytest.raises(ChildProcessError):
        os.waitid(os.P_PID, running[0], os.WEXITED | os.WNOHANG)
    assert set(threading.enumerate()) <= threads
    assert _fds() == fds


def test_a_create_that_fails_after_the_proxy_started_ends_it(server: int) -> None:
    """A stdin path that cannot be opened fails the start after the proxy is up; the failed
    create's cleanup ends it, and leaves no fd."""
    fds = _fds()

    with pytest.raises(JailSpawnFailed):
        create_bwrap_jail(
            ("true",),
            egress=_granting(server, "granted.test"),
            stdio=Stdio(stdin="/nonexistent-brig-test/stdin"),
        )

    assert _proxies() == []
    assert _fds() == fds
