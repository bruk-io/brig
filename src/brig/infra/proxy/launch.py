"""The host's end of a jail's egress proxy (decision-0009 item 2): starts the assembled proxy as
this process's child, through `infra.processes.spawn`, and ends it, verified by reaping it.

The proxy reads its program from its stdin (`python -I -`), so no file anywhere names it, and
nothing in the jail's view can. Its config is one JSON line on its fd 3, a pipe whose write end is
held here for the jail's life: closing it is how the proxy is told to end. Its fd 4 is its end of
the control socketpair whose other end the supervisor gets; `start` returns that other end for
the caller to hand on. Plain data in and out.
"""

import json
import os
import signal
import socket
import time
from dataclasses import dataclass
from typing import TypedDict

from brig.infra import processes
from brig.infra.proxy import program

_PROXY_ENV: dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
"""The whole environment the proxy gets: a fixed, non-secret `PATH`, never the embedder's."""


_END_GRACE_S = 0.5
"""How long `RunningProxy.end` waits for the proxy to leave on its own, once its config pipe is
closed, before it is killed."""

_POLL_INTERVAL_S = 0.01


class ProxySpawnError(Exception):
    """Raised when the egress proxy could not be started, or was started and could not be given
    its source or its config; whatever `start` spawned has been killed and reaped, and every fd
    it opened closed."""


class _Config(TypedDict, closed=True):
    """The one line the proxy reads on its fd 3."""

    allow: list[tuple[str, int]]
    hosts: dict[str, list[str]] | None


@dataclass(frozen=True)
class ProxyLaunch:
    """What starting a jail's egress proxy takes: `argv`, an interpreter line that runs the
    program its stdin carries (`python -I -`); `source`, the assembled file
    (`infra.proxy.assemble`); `allow`, the grants as `(host, port)` pairs; and `hosts`, a table
    the proxy resolves names from instead of the host's resolver, or `None` for the host's."""

    argv: tuple[str, ...]
    source: str
    allow: tuple[tuple[str, int], ...]
    hosts: frozendict[str, tuple[str, ...]] | None = None


def _config_line(launch: ProxyLaunch) -> str:
    config: _Config = {
        "allow": [(host, port) for host, port in launch.allow],
        "hosts": (
            None
            if launch.hosts is None
            else {name: list(addresses) for name, addresses in launch.hosts.items()}
        ),
    }
    return json.dumps(config) + "\n"


class RunningProxy:
    """A started egress proxy: its pid and pgid, and the write end of its config pipe.

    Invariant (rule 7): `_config_fd` is open, and the proxy unreaped, until `end`; then `None`,
    and the proxy has been reaped, so its pid is gone and no fd of it is left here.
    """

    def __init__(self, pid: int, pgid: int, config_fd: int) -> None:
        self.pid = pid
        self.pgid = pgid
        self._config_fd: int | None = config_fd

    def end(self) -> None:
        """End the proxy, once: close its config pipe, which tells it to leave, wait up to
        `_END_GRACE_S` for it to, then kill its group whatever it did and reap it. Reaped is
        verified: the pid is this process's child until then, and gone after. Safe to call
        twice."""
        config_fd = self._config_fd
        if config_fd is None:
            return
        self._config_fd = None
        try:
            os.close(config_fd)
        except OSError:
            pass
        deadline = time.monotonic() + _END_GRACE_S
        while processes.peek(self.pid) is None and time.monotonic() < deadline:
            time.sleep(_POLL_INTERVAL_S)
        processes.signal_group(self.pgid, signal.SIGKILL)
        processes.reap(self.pid)


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
        ProxySpawnError: the proxy could not be spawned, or it was and its source or config
            could not be written to it (it died first); it has then been killed and reaped, and
            every fd this opened is closed. The cause is the `__cause__`.
    """
    supervisor_end, proxy_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    source_read, source_write = os.pipe()
    config_read, config_write = os.pipe()
    null = os.open(os.devnull, os.O_RDWR | os.O_CLOEXEC)
    child_ends = [source_read, config_read, null]
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
            },
        )
    except (processes.SpawnError, OSError) as error:
        _close_all([*child_ends, source_write, config_write])
        supervisor_end.close()
        raise ProxySpawnError(f"could not start the egress proxy: {launch.argv!r}") from error
    finally:
        proxy_end.close()
    _close_all(child_ends)
    running = RunningProxy(spawned.pid, spawned.pgid, config_write)
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
