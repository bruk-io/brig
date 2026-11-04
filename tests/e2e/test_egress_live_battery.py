"""TASK-0001.37: a running jail's egress grants change, and its proxy's decisions come back as data
(decision-0009 items 5 and 6), against real bwrap.

The same stand-in for the internet as `test_egress_route_battery.py`: a TLS-less HTTP server on
the host's `127.0.0.1:<ephemeral>`, reached by name through the proxy's resolver seam
(`egress_hosts`), the literal `127.0.0.1:<port>` granted so a name resolving to it may reach it
(decision-0009 item 4). The name `late.test` is not granted when the jail is created.

One command runs in the jail for the whole test and acts on cue files the host writes, printing
one JSON line per step, so every step is the same jail and the same process: no restart.
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
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brig import (
    Destination,
    EgressChangeKind,
    EgressPolicy,
    EgressReason,
    EgressVerdict,
    Jail,
    JailEgressEnded,
    Stdio,
    allow_egress,
    create_bwrap_jail,
    destroy_jail,
    egress_decisions,
    egress_record,
    revoke_egress,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_BODY = b"hello from the test server"

_STEP_TIMEOUT_S = 30.0

_CLIENT = r"""
import json, os, socket, sys, time

port, cues = int(sys.argv[1]), sys.argv[2]
bridge = ("127.0.0.1", 3128)


def wait(step):
    while not os.path.exists(os.path.join(cues, str(step))):
        time.sleep(0.02)


def tunnel(name):
    sock = socket.create_connection(bridge, timeout=10)
    sock.sendall(f"CONNECT {name}:{port} HTTP/1.1\r\nHost: {name}:{port}\r\n\r\n".encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = sock.recv(1)
        if not chunk:
            break
        head += chunk
    return sock, head.decode().split("\r\n")[0]


def get(sock):
    sock.sendall(b"GET / HTTP/1.0\r\n\r\n")
    data = b""
    while chunk := sock.recv(65536):
        data += chunk
    return data.decode()


def say(step, **seen):
    print(json.dumps({"step": step, "pid": os.getpid(), **seen}), flush=True)


wait(1)
sock, head = tunnel("late.test")
sock.close()
say(1, head=head)

wait(2)
sock, head = tunnel("late.test")
body = get(sock) if head.startswith("HTTP/1.1 200") else ""
held, held_head = tunnel("late.test")
say(2, head=head, body=body, held=held_head)

wait(3)
sock, head = tunnel("late.test")
sock.close()
say(3, head=head, held_body=get(held))
"""
"""Step 1 asks for `late.test` before it is granted; step 2 after `allow_egress`, and opens a
second tunnel it holds; step 3 after `revoke_egress`, then sends a request through the tunnel
it held."""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", str(len(_BODY)))
        self.end_headers()
        self.wfile.write(_BODY)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture(scope="module")
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


def _the_proxy() -> list[int]:
    """The egress proxies seen at this step, once at least one shows: a read of `/proc` can land
    while the proxy is still being started or its cmdline is not yet readable (CI saw none at
    one step, 2026-11-04), and what is asserted is that one proxy served every step."""
    deadline = time.monotonic() + _STEP_TIMEOUT_S
    while not (found := _proxy_children()) and time.monotonic() < deadline:
        time.sleep(0.02)
    return found


@pytest.fixture(scope="module")
def journey(server: int) -> Iterator[tuple[int, Jail, list[dict[str, object]], list[int]]]:
    """The whole journey, once for this module: the jail refused `late.test`, was granted it,
    had it revoked, and finished. Its port, the jail, the three steps' lines, and the proxy pid
    seen at each."""
    late = Destination("late.test", server)
    with tempfile.TemporaryDirectory(dir="/tmp") as scratch:
        out, cues = Path(scratch) / "out", Path(scratch) / "cues"
        cues.mkdir()
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _CLIENT, str(server), str(cues)),
            egress=EgressPolicy((Destination("127.0.0.1", server),)),
            egress_hosts={"late.test": ("127.0.0.1",)},
            stdio=Stdio(stdout=str(out)),
        )
        try:
            proxies = [*_the_proxy()]
            steps = [_step(cues, out, 1)]
            allow_egress(jail, late)
            steps.append(_step(cues, out, 2))
            proxies += _the_proxy()
            revoke_egress(jail, late)
            steps.append(_step(cues, out, 3))
            proxies += _the_proxy()
            assert run_jail(jail, timeout_s=_STEP_TIMEOUT_S) == 0
        finally:
            destroy_jail(jail)
    yield server, jail, steps, proxies


def test_a_destination_allowed_while_the_jail_runs_is_reached_on_the_next_connection(
    journey: tuple[int, Jail, list[dict[str, object]], list[int]],
) -> None:
    """Refused, then allowed with `allow_egress`, then reached: by the same command (one pid in
    the jail) through the same proxy (one pid on the host), so nothing was restarted."""
    _, _, steps, proxies = journey
    first, second, _ = steps

    assert first["head"] == "HTTP/1.1 403 Forbidden"
    assert second["head"] == "HTTP/1.1 200 Connection established"
    assert isinstance(second["body"], str)
    assert second["body"].startswith("HTTP/1.0 200")
    assert second["body"].endswith(_BODY.decode())
    assert len({step["pid"] for step in steps}) == 1
    assert len(proxies) == 3
    assert len(set(proxies)) == 1


def test_revoke_egress_refuses_the_next_connection_and_leaves_an_open_one_alone(
    journey: tuple[int, Jail, list[dict[str, object]], list[int]],
) -> None:
    """After `revoke_egress`, a new connection to the destination gets the 403 signature, while
    the tunnel opened before the revoke still carries a request to it: a connection is judged
    once, when it names its destination."""
    _, _, steps, _ = journey
    _, second, third = steps

    assert second["held"] == "HTTP/1.1 200 Connection established"
    assert third["head"] == "HTTP/1.1 403 Forbidden"
    assert isinstance(third["held_body"], str)
    assert third["held_body"].endswith(_BODY.decode())


def test_each_decision_reaches_egress_decisions_with_its_destination_verdict_and_line(
    journey: tuple[int, Jail, list[dict[str, object]], list[int]],
) -> None:
    """One value per decision the proxy made, in order and numbered: step 1's refusal, step 2's
    two grants, step 3's refusal. Each carries the line the proxy wrote, verbatim: one JSON
    object in brig's envelope, `time`, `level`, `source` and `event` first and in that order,
    then the event's own fields, which say what the value says. Each is returned once: a second
    call finds none."""
    port, jail, _, _ = journey

    decisions = list(egress_decisions(jail))

    assert [decision.seq for decision in decisions] == [1, 2, 3, 4]
    assert {decision.destination for decision in decisions} == {Destination("late.test", port)}
    assert [decision.verdict for decision in decisions] == [
        EgressVerdict.REFUSED,
        EgressVerdict.ALLOWED,
        EgressVerdict.ALLOWED,
        EgressVerdict.REFUSED,
    ]
    assert [decision.reason for decision in decisions] == [
        EgressReason.NOT_GRANTED,
        EgressReason.GRANTED,
        EgressReason.GRANTED,
        EgressReason.NOT_GRANTED,
    ]
    times = [decision.time for decision in decisions]
    assert all(when.tzinfo is UTC for when in times)
    assert times == sorted(times)
    for decision in decisions:
        assert "\n" not in decision.line
        raw = json.loads(decision.line)
        assert list(raw) == [
            "time",
            "level",
            "source",
            "event",
            "seq",
            "verdict",
            "host",
            "port",
            "reason",
        ]
        assert raw["source"] == "egress-proxy"
        assert raw["event"] == "egress-decision"
        assert raw["level"] == ("info" if decision.verdict is EgressVerdict.ALLOWED else "warning")
        assert datetime.strptime(raw["time"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC) == (
            decision.time
        )
        assert raw["seq"] == decision.seq
        assert raw["verdict"] == decision.verdict.value
        assert (raw["host"], raw["port"]) == ("late.test", port)
        assert raw["reason"] == decision.reason.value
    assert list(egress_decisions(jail)) == []


def test_the_record_holds_the_policy_as_created_and_every_change_since(
    journey: tuple[int, Jail, list[dict[str, object]], list[int]],
) -> None:
    port, jail, _, _ = journey
    late = Destination("late.test", port)

    record = egress_record(jail)

    assert record.created == EgressPolicy((Destination("127.0.0.1", port),))
    assert [(change.kind, change.destination) for change in record.changes] == [
        (EgressChangeKind.ALLOW, late),
        (EgressChangeKind.REVOKE, late),
    ]


def test_a_grant_after_the_command_finished_is_refused_as_ended(
    journey: tuple[int, Jail, list[dict[str, object]], list[int]],
) -> None:
    """`run_jail` saw the command done, which ended its proxy: a grant has nothing to reach, and
    is neither sent nor recorded."""
    port, jail, _, _ = journey

    with pytest.raises(JailEgressEnded) as raised:
        allow_egress(jail, Destination("late.test", port))

    assert " -- " in str(raised.value)
    assert len(egress_record(jail).changes) == 2
