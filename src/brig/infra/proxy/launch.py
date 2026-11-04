"""The host's end of a jail's egress proxy (decision-0009 item 2): starts the assembled proxy as
this process's child, through `infra.processes.spawn`, and ends it, verified by reaping it.

The proxy reads its program from its stdin (`python -I -`), so no file anywhere names it, and
nothing in the jail's view can. Its config is one JSON line on its fd 3, a pipe whose write end is
held here for the jail's life: each change to the grants is one more line on it
(`RunningProxy.change`, decision-0009 item 5), and closing it is how the proxy is told to end. Its
fd 4 is its end of the control socketpair whose other end the supervisor gets; `start` returns
that other end for the caller to hand on. Its fd 5 is the decisions pipe: one envelope line per
decision (decision-0009 item 6), which a thread here drains into a bounded buffer for as long as
the proxy runs, so a proxy whose embedder reads nothing never blocks on it. Plain data in and
out.
"""

import json
import os
import select
import signal
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from brig.infra import processes
from brig.infra.proxy import program

_PROXY_ENV: dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
"""The whole environment the proxy gets: a fixed, non-secret `PATH`, never the embedder's."""


_END_GRACE_S = 0.5
"""How long `RunningProxy.end` waits for the proxy to leave on its own, once its config pipe is
closed, before it is killed."""

_POLL_INTERVAL_S = 0.01

KEPT_LINES = 1024
"""How many decision lines are kept for the embedder to take, at most: past that, the oldest is
dropped. With `LINE_LIMIT`, a jail's undelivered decisions hold at most 4 MiB of host memory."""

LINE_LIMIT = 4096
"""The longest decision line kept, in bytes, its newline included; a longer one is dropped whole.
The proxy's lines are far shorter: a destination's host is at most 255 bytes."""

_READ_CHUNK = 65536

_READER_JOIN_S = 2.0
"""How long `RunningProxy.end` waits for the decisions reader, once the proxy is reaped and so
the pipe has reached end of file."""


class ProxySpawnError(Exception):
    """Raised when the egress proxy could not be started, or was started and could not be given
    its source or its config; whatever `start` spawned has been killed and reaped, and every fd
    it opened closed."""


class ProxyEnded(Exception):
    """Raised by `RunningProxy.change` when the proxy can take no change: it has been ended, or
    its config pipe is broken because it died. Nothing was recorded."""


class _Config(TypedDict, closed=True):
    """The one line the proxy reads on its fd 3."""

    allow: list[tuple[str, int]]
    hosts: dict[str, list[str]] | None
    connections: int
    handshake_s: float


class _Change(TypedDict, closed=True):
    """One change to the grants, a line on the proxy's fd 3 after the first."""

    kind: str
    host: str
    port: int


@dataclass(frozen=True)
class ProxyLaunch:
    """What starting a jail's egress proxy takes: `argv`, an interpreter line that runs the
    program its stdin carries (`python -I -`); `source`, the assembled file
    (`infra.proxy.assemble`); `allow`, the grants as `(host, port)` pairs; `hosts`, a table
    the proxy resolves names from instead of the host's resolver, or `None` for the host's;
    `connections`, how many connections it serves at once (`program.CONNECTION_LIMIT`, or lower
    for a test); and `handshake_s`, how long a connection may take in all to name its
    destination (`program.HANDSHAKE_DEADLINE_S`, or lower for a test)."""

    argv: tuple[str, ...]
    source: str
    allow: tuple[tuple[str, int], ...]
    hosts: frozendict[str, tuple[str, ...]] | None = None
    connections: int = program.CONNECTION_LIMIT
    handshake_s: float = program.HANDSHAKE_DEADLINE_S


def _config_line(launch: ProxyLaunch) -> str:
    config: _Config = {
        "allow": [(host, port) for host, port in launch.allow],
        "hosts": (
            None
            if launch.hosts is None
            else {name: list(addresses) for name, addresses in launch.hosts.items()}
        ),
        "connections": launch.connections,
        "handshake_s": launch.handshake_s,
    }
    return json.dumps(config) + "\n"


class RunningProxy:
    """A started egress proxy: its pid and pgid, the grants it was started with (`allow`), the
    write end of its config pipe, the changes sent on it, and the decision lines read back.

    Invariant (rule 7): `_config_fd` is open, and the proxy unreaped, until `end`; then `None`,
    and the proxy has been reaped, so its pid is gone and no fd of it is left here once the
    reader has finished. `_changes` holds every change written to the pipe, in the order
    written, each written and recorded under `_grants`, so the record and the proxy's grants
    never disagree. `_lines` holds at most `KEPT_LINES` decision lines not yet taken, and
    `_dropped` counts the lines dropped (the oldest past that, or one longer than `LINE_LIMIT`),
    both under `_kept`.
    """

    def __init__(
        self, pid: int, pgid: int, config_fd: int, allow: tuple[tuple[str, int], ...] = ()
    ) -> None:
        self.pid = pid
        self.pgid = pgid
        self.allow = allow
        self._config_fd: int | None = config_fd
        self._grants = threading.Lock()
        self._changes: list[tuple[str, str, int, datetime]] = []
        self._kept = threading.Lock()
        self._lines: deque[str] = deque()
        self._dropped = 0
        self._reader: threading.Thread | None = None

    def watch(self, decisions_fd: int) -> None:
        """Start draining the decisions pipe's read end, `decisions_fd`, which this then owns
        and closes at its end of file.

        Raises:
            RuntimeError: no thread could start; `decisions_fd` has been closed.
        """
        reader = threading.Thread(target=self._read, args=(decisions_fd,), daemon=True)
        try:
            reader.start()
        except RuntimeError:
            os.close(decisions_fd)
            raise
        self._reader = reader

    def _keep(self, line: bytes | None) -> None:
        """Keep one whole decision line, or count one dropped (`None`)."""
        with self._kept:
            if line is None:
                self._dropped += 1
                return
            if len(self._lines) == KEPT_LINES:
                self._lines.popleft()
                self._dropped += 1
            self._lines.append(line.decode("utf-8", errors="replace"))

    def _read(self, fd: int) -> None:
        pending = b""
        skipping = False
        try:
            while chunk := os.read(fd, _READ_CHUNK):
                *lines, pending = (pending + chunk).split(b"\n")
                for line in lines:
                    if skipping or len(line) >= LINE_LIMIT:
                        self._keep(None)
                    else:
                        self._keep(line)
                    skipping = False
                if len(pending) >= LINE_LIMIT:
                    pending, skipping = b"", True
        except OSError:
            pass
        finally:
            os.close(fd)

    def take_lines(self) -> tuple[str, ...]:
        """The decision lines read since the last call, oldest first, each without its newline;
        each is returned once."""
        with self._kept:
            lines = tuple(self._lines)
            self._lines.clear()
        return lines

    @property
    def dropped(self) -> int:
        """How many decision lines were dropped before anything took them."""
        with self._kept:
            return self._dropped

    @property
    def changes(self) -> tuple[tuple[str, str, int, datetime], ...]:
        """Every change sent to the proxy: its kind, host, port, and when (UTC), in order."""
        with self._grants:
            return tuple(self._changes)

    def change(self, kind: str, host: str, port: int) -> datetime:
        """Send the proxy one change to its grants, `kind` (`allow` or `revoke`) of `host:port`,
        as one line on its config pipe, record it, and return when it was sent. The proxy
        applies it before it takes another connection (`program._main`).

        Raises:
            ProxyEnded: the proxy has been ended, or it died and its pipe is broken; nothing
                was recorded.
            ValueError: the line would be longer than `select.PIPE_BUF`, so it could not reach
                the pipe in one write; a validated destination never is.
        """
        change: _Change = {"kind": kind, "host": host, "port": port}
        line = json.dumps(change) + "\n"
        if len(line.encode("utf-8")) > select.PIPE_BUF:
            raise ValueError(f"a change line is longer than PIPE_BUF: {host!r}")
        with self._grants:
            config_fd = self._config_fd
            if config_fd is None:
                raise ProxyEnded("the egress proxy has ended")
            try:
                with os.fdopen(config_fd, "w", encoding="utf-8", closefd=False) as pipe:
                    pipe.write(line)
            except OSError as error:
                raise ProxyEnded("the egress proxy's config pipe is broken") from error
            when = datetime.now(UTC)
            self._changes.append((kind, host, port, when))
        return when

    def end(self) -> None:
        """End the proxy, once: close its config pipe, which tells it to leave, wait up to
        `_END_GRACE_S` for it to, then kill its group whatever it did and reap it, and wait for
        the decisions reader to read the pipe to its end. Reaped is verified: the pid is this
        process's child until then, and gone after. What was read stays for `take_lines`. Safe
        to call twice."""
        with self._grants:
            config_fd = self._config_fd
            self._config_fd = None
        if config_fd is None:
            return
        try:
            os.close(config_fd)
        except OSError:
            pass
        deadline = time.monotonic() + _END_GRACE_S
        while processes.peek(self.pid) is None and time.monotonic() < deadline:
            time.sleep(_POLL_INTERVAL_S)
        processes.signal_group(self.pgid, signal.SIGKILL)
        processes.reap(self.pid)
        if self._reader is not None:
            self._reader.join(_READER_JOIN_S)


def _close_all(fds: list[int]) -> None:
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass


def start(launch: ProxyLaunch) -> tuple[RunningProxy, int]:
    """Start the proxy `launch` describes, give it its source and its config, and return it with
    the supervisor's end of the control socketpair: an fd the caller owns, to hand the supervisor
    as `wire.BRIDGE_FD` and then close. A `SOCK_SEQPACKET` pair, so each fd the supervisor sends
    arrives as one message.

    Raises:
        ProxySpawnError: the proxy could not be spawned, or it was and its decisions reader
            could not start, or its source or config could not be written to it (it died
            first); it has then been killed and reaped, and every fd this opened is closed. The
            cause is the `__cause__`.
    """
    supervisor_end, proxy_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    source_read, source_write = os.pipe()
    config_read, config_write = os.pipe()
    decisions_read, decisions_write = os.pipe()
    null = os.open(os.devnull, os.O_RDWR | os.O_CLOEXEC)
    child_ends = [source_read, config_read, decisions_write, null]
    try:
        spawned = processes.spawn(
            launch.argv,
            (),
            env=_PROXY_ENV,
            fds={
                0: source_read,
                1: null,
                2: null,
                program.CONFIG_FD: config_read,
                program.CONTROL_FD: proxy_end.fileno(),
                program.DECISIONS_FD: decisions_write,
            },
        )
    except (processes.SpawnError, OSError) as error:
        _close_all([*child_ends, source_write, config_write, decisions_read])
        supervisor_end.close()
        raise ProxySpawnError(f"could not start the egress proxy: {launch.argv!r}") from error
    finally:
        proxy_end.close()
    _close_all(child_ends)
    running = RunningProxy(spawned.pid, spawned.pgid, config_write, launch.allow)
    try:
        running.watch(decisions_read)
    except RuntimeError as error:
        _close_all([source_write])
        running.end()
        supervisor_end.close()
        raise ProxySpawnError("no thread could read the egress proxy's decisions") from error
    try:
        with os.fdopen(source_write, "w", encoding="utf-8") as source_pipe:
            source_pipe.write(launch.source)
        with os.fdopen(config_write, "w", encoding="utf-8", closefd=False) as config_pipe:
            config_pipe.write(_config_line(launch))
    except OSError as error:
        running.end()
        supervisor_end.close()
        raise ProxySpawnError("the egress proxy ended before it took its program") from error
    return running, supervisor_end.detach()
