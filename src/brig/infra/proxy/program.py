"""The egress proxy: a host-side program per jail with an egress policy (decision-0009 item 2).

The jail's supervisor accepts each connection on the jail's loopback and sends this program one
end of a socketpair per connection, with `SCM_RIGHTS`, over fd 4. This program reads the request
on it (HTTP `CONNECT host:port`, absolute-form plain HTTP, or SOCKS5 `CONNECT`), decides with the
egress decision, resolves a name itself and only when a grant names it, connects only to the
addresses the decision allowed, and relays. A refusal answers `403` with the destination named,
or SOCKS reply `0x02`.

Standard library only, and it imports nothing of brig (the `brig-standalone-programs` gate). The
decision is `domain/policy/egress.py`, and the log envelope `infra/log.py`, each assembled in
beside this file as its own module (`infra/proxy/assemble.py`) and handed to `_main` as a value:
this module reads the decision through one seam, `_judge`, which turns what it answers into this
module's own `_Verdict`, and the envelope through another, `_Decisions.record`.

Its fds:
- 3, the config pipe: one JSON line (the grants and an optional resolver table), then one line
  per change to the grants (decision-0009 item 5); its end of file says the host let go of the
  jail.
- 4, the control socket from the supervisor, whose end of file says the jail is gone. Either
  end of file ends this program.
- 5, the decisions pipe: one envelope line per decision, read by the host's link
  (decision-0009 item 6). Nothing else is written there, and fds 1 and 2 are `/dev/null`.

A change applies to the next connection: each turn of `_main` reads the config pipe before the
control socket, and a connection is decided against the grants in force when its fd arrived, so
one the supervisor hands over after a change was written is decided against the new grants. A
connection already relaying is never judged again: revoking a grant leaves it open.
"""

import ipaddress
import json
import os
import select
import socket
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType
from typing import TypedDict, assert_never

DECISION_MODULE = "brig_egress_decision"
"""The module name the assembled file gives `egress.py`'s source, registered in `sys.modules`
before this program runs, so its dataclasses resolve their own module."""

CONFIG_FD = 3
"""The config pipe: one JSON line, then held open by the host for the jail's life."""

CONTROL_FD = 4
"""This program's end of the supervisor's `SOCK_SEQPACKET` socketpair (`wire.BRIDGE_FD` on the
supervisor's side)."""

DECISIONS_FD = 5
"""The decisions pipe: one envelope line per decision, to the host."""

LOG_MODULE = "brig_log"
"""The module name the assembled file gives `infra/log.py`'s source, the envelope's encoder."""

SOURCE = "egress-proxy"
"""This program's name in the envelope's `source`."""

DECISION_EVENT = "egress-decision"
"""The envelope's `event` for one decision."""

_HEAD_LIMIT = 65536
"""The longest HTTP request head read before the request is refused as unreadable."""

_HANDSHAKE_TIMEOUT_S = 30.0
"""How long a connection may take to name its destination."""

_CONNECT_TIMEOUT_S = 10.0
"""How long one connect to an allowed address may take."""

_RELAY_CHUNK = 65536
"""How many bytes one relayed read takes at most."""

_DROPPED_HEADERS = frozenset(
    {b"proxy-connection", b"proxy-authorization", b"connection", b"keep-alive"}
)
"""The request headers an absolute-form request loses on its way to the destination: the proxy's
own, and the connection's, replaced by `Connection: close`, so one connection carries one
request to one decided destination."""


@dataclass(frozen=True)
class _Config:
    """What the host sends on `CONFIG_FD`: the grants as `(host, port)` pairs, and the resolver
    table to look names up in instead of the host's resolver (`None`: the host's)."""

    allow: tuple[tuple[str, int], ...]
    hosts: frozendict[str, tuple[str, ...]] | None


@dataclass(frozen=True)
class _Go:
    """Allowed: connect to `addresses`, in order, and to nothing else."""

    addresses: tuple[str, ...]


@dataclass(frozen=True)
class _Denied:
    """Refused by the policy: no grant matches, or the name reached a private address."""


@dataclass(frozen=True)
class _Unresolved:
    """Granted, but the name resolved to no address."""


@dataclass(frozen=True)
class _Unreadable:
    """The request named no destination the decision could read."""


type _Verdict = _Go | _Denied | _Unresolved | _Unreadable
"""What `_judge` answers, in this module's own values."""


class _DecisionFields(TypedDict, closed=True):
    """The event's own fields of one decision line, after the envelope's head."""

    seq: int
    verdict: str
    host: str
    port: int
    reason: str


class _Change(TypedDict, closed=True):
    """One change to the grants, a line on `CONFIG_FD` after the first."""

    kind: str
    host: str
    port: int


class _Decisions:
    """The decisions pipe's one writer: numbers each decision and writes it as one envelope line.

    Invariant (rule 7): `_seq` is the number of the last decision written, and only one thread at
    a time writes, under `_lock`, so lines are whole and numbered in the order written.
    """

    def __init__(self, log: ModuleType, fd: int) -> None:
        self._log = log
        self._fd = fd
        self._lock = threading.Lock()
        self._seq = 0

    def record(self, verdict: str, reason: str, host: str, port: int) -> None:
        """Write one decision line. An `OSError` from the pipe is swallowed: the host stopped
        reading, and the decision stands without its line."""
        level = self._log.Level.INFO if verdict == "allowed" else self._log.Level.WARNING
        with self._lock:
            self._seq += 1
            fields: _DecisionFields = {
                "seq": self._seq,
                "verdict": verdict,
                "host": host,
                "port": port,
                "reason": reason,
            }
            line = str(self._log.encode(datetime.now(UTC), level, SOURCE, DECISION_EVENT, fields))
            try:
                self._log.write(self._fd, line)
            except OSError:
                pass


def local_addresses(if_inet6: str, fib_trie: str) -> tuple[str, ...]:
    """The host's own addresses, from the text of `/proc/net/if_inet6` (every IPv6 address on an
    interface) and `/proc/net/fib_trie` (each IPv4 address the local table marks `/32 host
    LOCAL`), in that order, each once. A line neither form explains is skipped."""
    found: dict[str, None] = {}
    for line in if_inet6.splitlines():
        fields = line.split()
        if fields and len(fields[0]) == 32:
            try:
                found[str(ipaddress.IPv6Address(int(fields[0], 16)))] = None
            except ValueError:
                continue
    last: str | None = None
    for line in fib_trie.splitlines():
        stripped = line.strip()
        if stripped.startswith("|--"):
            last = stripped[3:].strip()
        elif stripped.startswith("/32 host LOCAL") and last is not None:
            try:
                found[str(ipaddress.IPv4Address(last))] = None
            except ValueError:
                continue
    return tuple(found)


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="ascii", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _host_addresses() -> tuple[str, ...]:
    """The host's own addresses now, read afresh for each decision that needs them, since a
    host's addresses can change while a jail runs."""
    return local_addresses(_read_text("/proc/net/if_inet6"), _read_text("/proc/net/fib_trie"))


def _resolve(
    name: str, port: int, hosts: frozendict[str, tuple[str, ...]] | None
) -> tuple[str, ...]:
    """What `name` resolves to: from `hosts` when the host gave a table (a name not in it
    resolves to nothing), else through the host's own resolver. Each address once, in order."""
    if hosts is not None:
        return hosts.get(name, ())
    try:
        found = socket.getaddrinfo(name, port, type=socket.SOCK_STREAM)
    except OSError, UnicodeError:
        return ()
    return tuple(dict.fromkeys(str(entry[4][0]) for entry in found))


@dataclass(frozen=True)
class _Context:
    """What serving one connection takes beside it: the decision module, the grants in force
    when the connection arrived, the config, and the decisions pipe's writer."""

    decision: ModuleType
    policy: object
    config: _Config
    decisions: _Decisions


def _judge(context: _Context, host: str, port: int) -> _Verdict:
    """Whether `host:port` may be reached, by `decision.decide_egress` over the context's grants:
    once with no addresses, and, when it answers `Resolve`, again with what the name resolved to
    and the host's own addresses. A name no grant matches is never looked up. The settled
    outcome is written as one decision line. The one place this module reads the decision's
    values."""
    decision, policy = context.decision, context.policy
    request = decision.Authority(host, port)
    outcome = decision.decide_egress(policy, request)
    if isinstance(outcome, decision.Resolve):
        resolved = _resolve(str(outcome.name), port, context.config.hosts)
        outcome = decision.decide_egress(policy, request, resolved, _host_addresses())
    reason = decision.egress_reason(outcome)
    verdict = decision.egress_verdict(reason)
    context.decisions.record(str(verdict.value), str(reason.value), host, port)
    if isinstance(outcome, decision.Allowed):
        return _Go(tuple(str(address) for address in outcome.addresses))
    if isinstance(outcome, decision.Unresolved):
        return _Unresolved()
    if isinstance(outcome, decision.AuthorityUnparseable):
        return _Unreadable()
    return _Denied()


def _connect(addresses: tuple[str, ...], port: int) -> socket.socket | None:
    """A connection to the first of `addresses` that answers on `port`, or `None`."""
    for address in addresses:
        try:
            upstream = socket.create_connection((address, port), timeout=_CONNECT_TIMEOUT_S)
        except OSError:
            continue
        upstream.settimeout(None)
        return upstream
    return None


def _exactly(client: socket.socket, count: int) -> bytes:
    """`count` bytes from `client`.

    Raises:
        ConnectionError: `client` ended first.
    """
    data = b""
    while len(data) < count:
        chunk = client.recv(count - len(data))
        if not chunk:
            raise ConnectionError("the connection ended before its request did")
        data += chunk
    return data


def _named(host: str, port: int) -> str:
    """`host:port` as a request names it, an IPv6 literal bracketed."""
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _http_reply(client: socket.socket, status: str, body: str) -> None:
    payload = body.encode("utf-8", errors="replace")
    head = (
        f"HTTP/1.1 {status}\r\nContent-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
    )
    client.sendall(head.encode("ascii") + payload)


def _http_authority(method: str, target: str) -> tuple[str, int | None, str] | None:
    """The authority text a request names, the port to assume when it names none, and the
    origin-form target to send on (empty for `CONNECT`); `None` for a target this proxy does not
    carry (an origin-form or `https://` one)."""
    if method == "CONNECT":
        return target, None, ""
    if not target[:7].lower() == "http://":
        return None
    after = target[7:]
    end = min((index for index in map(after.find, "/?#") if index != -1), default=len(after))
    origin = after[end:]
    if not origin.startswith("/"):
        origin = "/" + origin
    return after[:end], 80, origin


def _origin_head(method: str, origin: str, version: str, headers: list[bytes]) -> bytes:
    kept = [
        header
        for header in headers
        if header.partition(b":")[0].strip().lower() not in _DROPPED_HEADERS
    ]
    request_line = f"{method} {origin} {version}".encode("latin-1")
    return b"\r\n".join([request_line, *kept, b"Connection: close"]) + b"\r\n\r\n"


def _http(
    context: _Context, client: socket.socket, first: bytes
) -> tuple[socket.socket, bytes] | None:
    """Read an HTTP request on `client`, decide it, and answer: the connection to relay and the
    bytes to send it first, or `None` once a refusal or failure is answered."""
    head = first
    while b"\r\n\r\n" not in head:
        if len(head) > _HEAD_LIMIT:
            _http_reply(client, "400 Bad Request", "brig: egress proxy could not read the request")
            return None
        chunk = client.recv(4096)
        if not chunk:
            return None
        head += chunk
    head_bytes, _, rest = head.partition(b"\r\n\r\n")
    request_line, *headers = head_bytes.split(b"\r\n")
    parts = request_line.decode("latin-1").split(" ")
    target = _http_authority(parts[0], parts[1]) if len(parts) == 3 else None
    if target is None:
        _http_reply(client, "400 Bad Request", "brig: egress proxy could not read the request")
        return None
    method, _, version = parts
    authority_text, default_port, origin = target
    decision = context.decision
    parsed = decision.parse_authority(authority_text, default_port)
    if isinstance(parsed, decision.AuthorityUnparseable):
        _http_reply(client, "400 Bad Request", "brig: egress proxy could not read the request")
        return None
    host, port = str(parsed.host), int(parsed.port)
    verdict = _judge(context, host, port)
    match verdict:
        case _Denied():
            _http_reply(
                client, "403 Forbidden", f"brig: egress denied by policy: {_named(host, port)}"
            )
            return None
        case _Unresolved():
            _http_reply(
                client, "502 Bad Gateway", f"brig: egress could not resolve {_named(host, port)}"
            )
            return None
        case _Unreadable():
            _http_reply(client, "400 Bad Request", "brig: egress proxy could not read the request")
            return None
        case _Go(addresses=addresses):
            pass
        case _ as unreachable:
            assert_never(unreachable)
    upstream = _connect(addresses, port)
    if upstream is None:
        _http_reply(
            client, "502 Bad Gateway", f"brig: egress could not connect to {_named(host, port)}"
        )
        return None
    if method == "CONNECT":
        client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        return upstream, rest
    return upstream, _origin_head(method, origin, version, headers) + rest


def _socks_reply(client: socket.socket, code: int) -> None:
    """Reply `code` to a SOCKS5 request. The bound address is always `0.0.0.0:0`: the address the
    proxy connected from is the host's, and nothing of the host's is the jail's to learn."""
    client.sendall(bytes((5, code, 0, 1, 0, 0, 0, 0, 0, 0)))


def _socks_host(client: socket.socket, kind: int) -> str | None:
    match kind:
        case 1:
            return str(ipaddress.IPv4Address(_exactly(client, 4)))
        case 4:
            return str(ipaddress.IPv6Address(_exactly(client, 16)))
        case 3:
            length = _exactly(client, 1)[0]
            return _exactly(client, length).decode("latin-1")
        case _:
            return None


def _socks(context: _Context, client: socket.socket) -> tuple[socket.socket, bytes] | None:
    """Speak SOCKS5 on `client` (its version byte already read): no authentication, `CONNECT`
    only, to an IPv4 or IPv6 literal or a name the proxy resolves (`socks5h`). The connection to
    relay, or `None` once a refusal or failure is answered (reply `0x02` for a refusal by the
    policy, `0x04` for a name that resolved to nothing, `0x05` for a connect that failed)."""
    methods = _exactly(client, _exactly(client, 1)[0])
    if 0 not in methods:
        client.sendall(b"\x05\xff")
        return None
    client.sendall(b"\x05\x00")
    version, command, _, kind = _exactly(client, 4)
    if version != 5:
        return None
    if command != 1:
        _socks_reply(client, 0x07)
        return None
    host = _socks_host(client, kind)
    if host is None:
        _socks_reply(client, 0x08)
        return None
    port = int.from_bytes(_exactly(client, 2), "big")
    match _judge(context, host, port):
        case _Denied():
            _socks_reply(client, 0x02)
            return None
        case _Unresolved():
            _socks_reply(client, 0x04)
            return None
        case _Unreadable():
            _socks_reply(client, 0x01)
            return None
        case _Go(addresses=addresses):
            pass
        case _ as unreachable:
            assert_never(unreachable)
    upstream = _connect(addresses, port)
    if upstream is None:
        _socks_reply(client, 0x05)
        return None
    _socks_reply(client, 0x00)
    return upstream, b""


def _copy(source: socket.socket, sink: socket.socket) -> None:
    """Copy bytes from `source` to `sink` until `source` ends, then end `sink`'s writing half;
    an error on either ends both whole, so the copy the other way stops too."""
    try:
        while chunk := source.recv(_RELAY_CHUNK):
            sink.sendall(chunk)
    except OSError:
        for either in (source, sink):
            try:
                either.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return
    try:
        sink.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def _relay(client: socket.socket, upstream: socket.socket) -> None:
    """Relay `client` and `upstream` both ways until each has ended, then close `upstream`."""
    back = threading.Thread(target=_copy, args=(upstream, client), daemon=True)
    back.start()
    _copy(client, upstream)
    back.join()
    upstream.close()


def _serve(context: _Context, client: socket.socket) -> None:
    """One connection from the jail: SOCKS5 when its first byte is `0x05`, HTTP otherwise;
    decided, answered, and relayed when allowed. Closes `client` whatever happened."""
    try:
        client.settimeout(_HANDSHAKE_TIMEOUT_S)
        first = client.recv(1)
        if not first:
            return
        if first == b"\x05":
            route = _socks(context, client)
        else:
            route = _http(context, client, first)
        if route is None:
            return
        upstream, pending = route
        client.settimeout(None)
        if pending:
            upstream.sendall(pending)
        _relay(client, upstream)
    except OSError, UnicodeError, ValueError:
        pass
    finally:
        client.close()


def _read_config() -> _Config:
    """The one config line on `CONFIG_FD`, read raw so the fd's end of file can be watched
    after it.

    A line that is not the config's JSON shape raises out of `json` or the conversion, ending
    the program before it serves anything.

    Raises:
        ConnectionError: `CONFIG_FD` closed before a whole line arrived.
    """
    line = b""
    while not line.endswith(b"\n"):
        chunk = os.read(CONFIG_FD, 4096)
        if not chunk:
            raise ConnectionError(f"fd {CONFIG_FD} closed before the config arrived")
        line += chunk
    raw = json.loads(line)
    allow = tuple((str(host), int(port)) for host, port in raw["allow"])
    table = raw["hosts"]
    hosts = (
        None
        if table is None
        else frozendict(
            {
                str(name).lower().removesuffix("."): tuple(str(address) for address in addresses)
                for name, addresses in table.items()
            }
        )
    )
    return _Config(allow=allow, hosts=hosts)


def _changed(decision: ModuleType, policy: object, line: bytes) -> object:
    """`policy` with the change `line` names made, by the decision's own `egress_after`.

    A line that is not a change's JSON shape raises out of `json` or the conversion, ending the
    program: the host writes these, so a bad one is brig's bug, and ending fails closed.
    """
    raw: _Change = json.loads(line)
    kind = decision.EgressChangeKind(str(raw["kind"]))
    destination = decision.Destination(str(raw["host"]), int(raw["port"]))
    return decision.egress_after(policy, kind, destination)


def _main(decision: ModuleType, log: ModuleType) -> None:
    """Read the config, then serve every connection the supervisor sends, each on a daemon
    thread, until `CONFIG_FD` or `CONTROL_FD` reaches end of file: the host let go, or the jail
    is gone. Each turn applies every whole change line on `CONFIG_FD` before it takes the next
    connection, which is decided against the grants in force then. Returning ends the program,
    and every connection with it."""
    config = _read_config()
    policy: object = decision.EgressPolicy(
        tuple(decision.Destination(host, port) for host, port in config.allow)
    )
    decisions = _Decisions(log, DECISIONS_FD)
    control = socket.socket(fileno=CONTROL_FD)
    pending = b""
    while True:
        ready, _, _ = select.select([CONFIG_FD, CONTROL_FD], [], [])
        if CONFIG_FD in ready:
            chunk = os.read(CONFIG_FD, 4096)
            if not chunk:
                return
            *lines, pending = (pending + chunk).split(b"\n")
            for line in lines:
                policy = _changed(decision, policy, line)
        if CONTROL_FD in ready:
            try:
                message, fds, _, _ = socket.recv_fds(control, 16, 4)
            except OSError:
                return
            if not message and not fds:
                return
            for fd in fds:
                client = socket.socket(fileno=fd)
                context = _Context(decision, policy, config, decisions)
                threading.Thread(target=_serve, args=(context, client), daemon=True).start()


if __name__ == "__main__":
    _main(sys.modules[DECISION_MODULE], sys.modules[LOG_MODULE])
