"""The host's end of the supervisor's wire (decision-0002): starts the assembled supervisor as
this process's child, through `infra.processes.spawn`, hands it the one exec request, and reads
its events. Imports `wire.py` directly, since this module never runs inside a jail. Plain data
in and out; `presentation/jail.py` translates its values.

The supervisor process gets `_SUPERVISOR_ENV`, never the command's environment and never this
process's own: an allowed `PYTHONPATH` ran code inside the supervisor and an `LD_PRELOAD`
reached bwrap on the host, and the command can read its parent's `/proc/<pid>/environ`
(TASK-0001.15/.17 review).

A jail with an egress route (`Bridge`, decision-0009 item 1) gets its proxy started first
(`infra.proxy.launch`), the supervisor its end of their socketpair as `wire.BRIDGE_FD`, and the
proxy ends when the supervisor is closed. The proxy is this process's own child, not one of the
jail's group, so every path here that fails after its start ends it here.
"""

import os
import select
import socket
import stat
import time
from collections.abc import Mapping
from dataclasses import dataclass

from brig.infra import processes
from brig.infra.proxy import launch
from brig.infra.supervisor import wire
from brig.infra.supervisor.pumps import Flow, Pumps

_READ_CHUNK = 4096
"""How many bytes `Supervisor.read_event` reads at once: one event line, usually."""

_DRAIN_S = 2.0
"""How long closing a supervisor waits for its command's output to finish pumping: what is left
in the pipes once the jail is gone, which is at most their capacity (TASK-0042)."""

_SUPERVISOR_ENV: dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
"""The whole environment the supervisor process gets: a fixed, non-secret `PATH`. It does not
resolve `bwrap`: `posix_spawnp` searches the caller's own `PATH`, not the child's (measured on
glibc and Apple's libc, TASK-0014)."""


class SupervisorSpawnError(Exception):
    """Raised when the supervisor process itself could not be started, or was spawned and a
    later step of its start failed.

    Args:
        argv: The command that could not be run.
        spawned: The `(pid, pgid)` of a supervisor that was spawned before the start failed:
            still this process's child, unreaped and possibly running, for the caller to tear
            down and reap; `None` when nothing was spawned.
    """

    def __init__(self, argv: tuple[str, ...], spawned: tuple[int, int] | None = None) -> None:
        super().__init__(f"could not start the supervisor: {argv!r}")
        self.argv = argv
        self.spawned = spawned


@dataclass(frozen=True)
class SupervisorDoneUnknown:
    """What `await_done` returns when the supervisor's report can never be recovered: the
    events pipe closed with no `done`, or a line could not be read or decoded. Distinct from
    `None`, a deadline that passed first."""


@dataclass(frozen=True)
class ReadTimedOut:
    """What `Supervisor.read_event` returns when `deadline` passes before a whole line arrives.
    Unlike `None` (end of file), a later call may still succeed; the partial line stays
    buffered."""


@dataclass(frozen=True)
class Bridge:
    """A jail's one route out (decision-0009 item 1): the supervisor listens on `port` in the
    jail's loopback and hands each connection to the egress proxy `proxy` describes, relaying
    at most `limit` at once (`wire.BRIDGE_CONNECTION_LIMIT`, or lower for a test).

    With `listeners` (a Seatbelt jail's, `sockets.bridge_listeners`), the host has bound the
    port already, on `127.0.0.1` and `[::1]`: the supervisor gets them as
    `wire.BRIDGE_LISTENER_FDS` and binds nothing. The caller keeps its own copies open for the
    jail's life and closes them (decision-0011): held by the host, the port stays the jail's
    after the supervisor has exited, so no other program takes it while a process of the jail
    may still connect."""

    port: int
    proxy: launch.ProxyLaunch
    limit: int = wire.BRIDGE_CONNECTION_LIMIT
    listeners: tuple[socket.socket, ...] = ()


class Supervisor:
    """A started supervisor: its pid and pgid, the read end of its events pipe, the pumps
    that carry its command's stdio (TASK-0042), and its egress proxy, if the jail has one.

    Invariant (rule 7): `_pending` holds the bytes read from `events_fd` that do not yet end in
    a newline, since one `os.read` may return part of a line or more than one. `events_fd`
    stays open, `pumps` pumping and `proxy` running, until `close`.
    """

    def __init__(
        self,
        pid: int,
        pgid: int,
        events_fd: int,
        pumps: Pumps | None = None,
        proxy: launch.RunningProxy | None = None,
    ) -> None:
        self.pid = pid
        self.pgid = pgid
        self.events_fd = events_fd
        self.pumps = pumps
        self.proxy = proxy
        self._pending = b""

    def read_event(self, deadline: float) -> wire.Event | None | ReadTimedOut:
        """Read and decode the next event line, waiting at most until `deadline` for each read:
        an unbounded read let a command that wrote half a line hold `run_jail` past its timeout
        (measured, TASK-0001.15/.17 review).

        Returns `None` at end of file with nothing pending, `ReadTimedOut` if `deadline` passes
        first. A line that is no event raises `wire.WireError` out of `wire.decode_event`.
        """
        while b"\n" not in self._pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ReadTimedOut()
            ready, _, _ = select.select([self.events_fd], [], [], remaining)
            if not ready:
                return ReadTimedOut()
            chunk = os.read(self.events_fd, _READ_CHUNK)
            if not chunk:
                if not self._pending:
                    return None
                line, self._pending = self._pending, b""
                return wire.decode_event(line.decode())
            self._pending += chunk
        line, _, self._pending = self._pending.partition(b"\n")
        return wire.decode_event(line.decode())

    def close(self) -> None:
        """Close `events_fd`, once, after the last `read_event`, finish the pumps, and end the
        egress proxy: what the command wrote is pumped on until its pipes reach end of file, for
        at most `_DRAIN_S`, and its stdin is fed no more; the proxy is told to leave, killed if
        it does not, and reaped (law 7). An `OSError` is swallowed, since teardown calls this
        unconditionally."""
        try:
            os.close(self.events_fd)
        except OSError:
            pass
        if self.pumps is not None:
            self.pumps.finish(time.monotonic() + _DRAIN_S)
        if self.proxy is not None:
            self.proxy.end()


type Stdio = tuple[str | None, str | None, str | None]
"""Where the supervisor's fd 0, 1 and 2, which its command inherits, are pumped from and to:
each a host path to open, or `None` for this process's own. The supervisor gets pipes, never
these (TASK-0042)."""

_NO_STDIO: Stdio = (None, None, None)


def _open_through_no_link(path: str, flags: int) -> int:
    """Open `path` with `flags` one component at a time, following no symbolic link (TASK-0031),
    and refuse a file with another name (a hard link, TASK-0035).

    Raises:
        OSError: a component is missing or a link, the file cannot be opened, or it has another
            name.
    """
    if path == "/dev/null":
        return os.open(path, flags | os.O_CLOEXEC)
    parts = [part for part in path.split("/") if part]
    walk = getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    current = os.open("/", walk)
    try:
        for part in parts[:-1]:
            following = os.open(part, walk, dir_fd=current)
            os.close(current)
            current = following
        opened = os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=current)
    finally:
        os.close(current)
    info = os.fstat(opened)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        os.close(opened)
        raise OSError(f"{path} is not a regular file this user owns; refusing to use it as stdio")
    if info.st_nlink > 1:
        os.close(opened)
        raise OSError(f"{path} has another name (a hard link); refusing to write through it")
    return opened


def _open_end(number: int, path: str | None) -> int:
    """The host's end of stream `number`: `path` opened through no link (0 for reading; 1 and 2
    for appending, created 0600), or a duplicate of this process's own fd `number` (or
    `/dev/null` where that is closed), so closing it leaves the embedder's own open. An
    `OSError` from opening `path` propagates.
    """
    if path is None:
        try:
            return os.dup(number)
        except OSError:
            path = "/dev/null"
    flags = os.O_RDONLY if number == 0 else os.O_WRONLY | os.O_APPEND | os.O_CREAT
    return _open_through_no_link(path, flags)


def _plumb(stdio: Stdio) -> tuple[dict[int, int], tuple[Flow, ...]]:
    """A pipe per stream: the jail's end of each, keyed by the fd number the supervisor gets it
    on, and the flows that pump the host's end to or from where `stdio` says (TASK-0042). The
    jail is never handed an fd on a host inode: reopening `/proc/self/fd/N` reaches only the
    pipe.

    Raises:
        OSError: a path could not be opened, or a pipe made; whatever was opened before is
            closed.
    """
    opened: list[int] = []
    jail_ends: dict[int, int] = {}
    flows: list[Flow] = []
    try:
        for number, path in enumerate(stdio):
            host = _open_end(number, path)
            opened.append(host)
            read_end, write_end = os.pipe()
            opened += [read_end, write_end]
            if number == 0:
                jail_ends[number] = read_end
                flows.append(Flow(source=host, sink=write_end, inbound=True))
            else:
                jail_ends[number] = write_end
                flows.append(Flow(source=read_end, sink=host, inbound=False))
    except OSError:
        for fd in opened:
            os.close(fd)
        raise
    return jail_ends, tuple(flows)


def _start(
    supervisor_argv: tuple[str, ...],
    command_argv: tuple[str, ...],
    command_env: Mapping[str, str],
    stdio: Stdio = _NO_STDIO,
    bridge: Bridge | None = None,
) -> Supervisor:
    """Start `supervisor_argv` as this process's child, give it a pipe as each of fd 0, 1 and 2,
    pumped to and from where `stdio` says (`_plumb`), and write it the one exec request for
    `command_argv` in `command_env`. With `bridge`, its egress proxy is started first, the
    supervisor gets its end of their socketpair as `wire.BRIDGE_FD`, and the request names the
    bridge's port; a bridge's host-bound listeners (`Bridge.listeners`) become its
    `wire.BRIDGE_LISTENER_FDS`; the caller's own copies stay open, its to close.

    The request pipe's read end and the events pipe's write end become the child's
    `wire.REQUEST_FD` and `wire.EVENTS_FD`; this process closes its copies of both, and of the
    stdio pipes' jail ends, once the child has them, so each pipe reaches end of file when the
    jail is gone. No other fd of this process reaches the supervisor, and so its command.
    `command_env` goes only into the request; the supervisor runs in `_SUPERVISOR_ENV`.

    Raises:
        SupervisorSpawnError: `supervisor_argv` could not be started (`spawned` is `None`), or
            it was spawned and then its pumps could not start, or the one exec request could
            not be written to it (it died, or otherwise closed its own `wire.REQUEST_FD`).
            Then `spawned` is its `(pid, pgid)`: it is neither signalled nor reaped here, since
            only the caller's verified teardown can say its group is gone (TASK-0046), and
            every fd this start opened is closed. Either way an egress proxy this start began
            has been ended, and `spawned` is `None` when it was the proxy that could not start.
        OSError: `_plumb` could not open a stdio path or make a pipe; nothing of the jail was
            spawned, and an egress proxy this start began has been ended.
    """
    proxy: launch.RunningProxy | None = None
    bridge_fd: int | None = None
    if bridge is not None:
        try:
            proxy, bridge_fd = launch.start(bridge.proxy)
        except launch.ProxySpawnError as exc:
            raise SupervisorSpawnError(supervisor_argv) from exc
    try:
        jail_ends, flows = _plumb(stdio)
    except OSError:
        if proxy is not None and bridge_fd is not None:
            proxy.end()
            os.close(bridge_fd)
        raise
    request_read_fd, request_write_fd = os.pipe()
    events_read_fd, events_write_fd = os.pipe()
    bridged = {} if bridge_fd is None else {wire.BRIDGE_FD: bridge_fd}
    inherited = (
        {}
        if bridge is None
        else dict(
            zip(wire.BRIDGE_LISTENER_FDS, (listener.fileno() for listener in bridge.listeners))
        )
    )
    try:
        spawned = processes.spawn(
            supervisor_argv,
            (),
            env=_SUPERVISOR_ENV,
            fds={
                **jail_ends,
                wire.REQUEST_FD: request_read_fd,
                wire.EVENTS_FD: events_write_fd,
                **bridged,
                **inherited,
            },
        )
    except (processes.SpawnError, OSError) as exc:
        for fd in (request_read_fd, request_write_fd, events_read_fd, events_write_fd):
            os.close(fd)
        for flow in flows:
            os.close(flow.source)
            os.close(flow.sink)
        if proxy is not None:
            proxy.end()
        raise SupervisorSpawnError(supervisor_argv) from exc
    finally:
        for fd in (*jail_ends.values(), *bridged.values()):
            os.close(fd)
    os.close(request_read_fd)
    os.close(events_write_fd)
    pumps: Pumps | None = None
    port = None if bridge is None else bridge.port
    limit = wire.BRIDGE_CONNECTION_LIMIT if bridge is None else bridge.limit
    passed = bool(inherited)
    try:
        pumps = Pumps(flows)
        with os.fdopen(request_write_fd, "w") as request_pipe:
            request_pipe.write(
                wire.encode_exec_request(command_argv, command_env, port, limit, passed)
            )
    except (OSError, RuntimeError) as exc:
        # Spawned, then failed: a thread that could not start (`RuntimeError`), or a request
        # that hit a pipe its reader closed. Left for the caller's verified teardown.
        os.close(events_read_fd)
        if pumps is None:
            os.close(request_write_fd)
            for flow in flows:
                os.close(flow.source)
                os.close(flow.sink)
        else:
            pumps.finish(time.monotonic())
        if proxy is not None:
            proxy.end()
        raise SupervisorSpawnError(supervisor_argv, (spawned.pid, spawned.pgid)) from exc
    return Supervisor(
        pid=spawned.pid, pgid=spawned.pgid, events_fd=events_read_fd, pumps=pumps, proxy=proxy
    )


def _await_one_done(supervisor: Supervisor, deadline: float) -> int | None | SupervisorDoneUnknown:
    """Read `supervisor`'s events until `done`, or until `deadline` passes.

    Returns:
        The command's exit code from `done`; `None` if `deadline` passed first (the pipe stays
        open for a later call); `SupervisorDoneUnknown` at end of file with no `done`, or when
        a line cannot be read or decoded.
    """
    while True:
        try:
            outcome = supervisor.read_event(deadline)
        except OSError, wire.WireError:
            return SupervisorDoneUnknown()
        if isinstance(outcome, ReadTimedOut):
            return None
        if outcome is None:
            return SupervisorDoneUnknown()
        exit_code = wire.done_exit_code(outcome)
        if exit_code is not None:
            return exit_code
        # a `started` or `exited` event: not done yet, read the next one.


class LiveSupervisor:
    """The real `SupervisorPort` for one jail: starts its supervisor and tracks it until done.

    Invariant (rule 7): `_supervisor` is the supervisor `start` began, with its events pipe
    open, until `await_done` sees a terminal outcome or `close` runs; then `None`. A pid other
    than its own reads as one already closed. `_proxy` is the egress proxy that start began, if
    the jail has a bridge, and is kept once the supervisor is closed (and the proxy ended), so
    what it was sent and what it decided can still be read.
    """

    def __init__(
        self,
        supervisor_argv: tuple[str, ...],
        stdio: Stdio = _NO_STDIO,
        bridge: Bridge | None = None,
    ) -> None:
        """`supervisor_argv` is the jail type's launch line for the supervisor's file; `stdio`
        where its (and so its command's) fd 0, 1 and 2 come from; `bridge` the jail's egress
        route, or `None` for a jail with none."""
        self._supervisor_argv = supervisor_argv
        self._stdio = stdio
        self._bridge = bridge
        self._supervisor: Supervisor | None = None
        self._proxy: launch.RunningProxy | None = None

    @property
    def proxy(self) -> launch.RunningProxy | None:
        """The egress proxy `start` began, ended or not; `None` before a start, or with no
        bridge."""
        return self._proxy

    def start(self, argv: tuple[str, ...], env: Mapping[str, str]) -> Supervisor:
        """Start the supervisor with `argv` in `env` as its one command; `_start` raises
        `SupervisorSpawnError` if it cannot, with the supervisor it spawned, if any, for the
        caller to tear down."""
        supervisor = _start(self._supervisor_argv, argv, env, self._stdio, self._bridge)
        self._supervisor = supervisor
        self._proxy = supervisor.proxy
        return supervisor

    def _held(self, pid: int) -> Supervisor | None:
        supervisor = self._supervisor
        return supervisor if supervisor is not None and supervisor.pid == pid else None

    def await_done(self, pid: int, deadline: float) -> int | None | SupervisorDoneUnknown:
        """Wait, until `deadline`, for the supervisor `pid` to report its command done
        (`_await_one_done`). A terminal outcome closes its pipe; `None` leaves it open for a
        later call. `SupervisorDoneUnknown` for a pid this instance does not hold open."""
        supervisor = self._held(pid)
        if supervisor is None:
            return SupervisorDoneUnknown()
        outcome = _await_one_done(supervisor, deadline)
        if outcome is None:
            return None
        supervisor.close()
        self._supervisor = None
        return outcome

    def close(self, pid: int) -> None:
        """Close the supervisor `pid`'s pipe if this instance still holds it open."""
        supervisor = self._held(pid)
        if supervisor is not None:
            supervisor.close()
            self._supervisor = None
