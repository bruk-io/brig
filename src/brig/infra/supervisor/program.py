"""The supervisor: PID 1 inside the jail's namespace (decision-0002).

Reads one `exec` request from fd 3, starts the command as its child, reaps everything
reparented to it (nothing else in the namespace will), and writes `started`, `exited` and
`done` to fd 4. With an egress proxy (decision-0009 item 1) it also listens on the jail's
loopback and bridges each connection to the proxy over fd 5, at most the exec request's
`bridge_limit` at once (`wire.BRIDGE_CONNECTION_LIMIT`, 256, or lower; TASK-0049): one more is
accepted and closed at once, so a program in the jail cannot make it hold threads and fds
without limit. Assembled with `wire.py` into one
stdlib-only file (rule 17), where an import of `wire` cannot resolve, so it repeats `wire.py`'s
numbers and message shapes.
"""

import ctypes
import json
import os
import signal
import socket
import threading
from types import FrameType

_REQUEST_FD = 3
"""`wire.REQUEST_FD`, repeated."""

_EVENTS_FD = 4
"""`wire.EVENTS_FD`, repeated."""

_BRIDGE_FD = 5
"""`wire.BRIDGE_FD`, repeated."""

_RELAY_CHUNK = 65536
"""How many bytes one bridged read takes at most."""


_PR_SET_DUMPABLE = 4
"""`prctl(2)`'s option number for the dumpable flag (`<linux/prctl.h>`): `ctypes` has no name
for it, and the standard library has no `prctl` of its own."""


class _NoCommandError(Exception):
    """Raised when `_REQUEST_FD` closes before one `exec` request line arrives."""

    def __init__(self) -> None:
        super().__init__(f"fd {_REQUEST_FD} closed before an exec request arrived")


class _NotProtectedError(Exception):
    """Raised when this process cannot make itself non-dumpable, so the command would be able
    to reach it (decision-0006): the supervisor refuses to start the command at all."""


def _make_undumpable() -> None:
    """Make this process non-dumpable before the command exists (decision-0006 item 1).

    The command is this process's child, under the same uid, with the jail's own procfs:
    while this process is dumpable the command can reopen `_EVENTS_FD` through
    `/proc/1/fd/4` and write a `done` of its own, whatever `_start_child`'s closes did, and
    `ptrace` this process outright. Non-dumpable, both are refused to a peer without
    `CAP_SYS_PTRACE` in the jail's user namespace, which `--cap-drop ALL` (the bwrap
    compile) ensures the command never holds. The command's own exec makes it dumpable again,
    which protects nothing of brig's.

    Raises:
        _NotProtectedError: `prctl` refused the flag.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise _NotProtectedError(
            f"prctl(PR_SET_DUMPABLE, 0) failed: {os.strerror(ctypes.get_errno())}"
        )


def _read_exec_request() -> tuple[list[str], dict[str, str], int | None, int]:
    """Read and parse the one exec request on `_REQUEST_FD`.

    Leaves `_REQUEST_FD` open (`closefd=False`): `_start_child`'s `CLOSE` action names it, and
    `posix_spawn` fails the whole spawn with `EBADF` for a `CLOSE` on a fd that is not open
    (measured). `_main` closes it after the spawn.

    Raises:
        _NoCommandError: `_REQUEST_FD` closed (EOF) before a line arrived.
        ValueError: the line read is not well-formed JSON, is missing
            `argv`, `env`, `bridge_port` or `bridge_limit`, or names an empty `argv`.
    """
    with os.fdopen(_REQUEST_FD, "r", closefd=False) as request_pipe:
        line = request_pipe.readline()
    if not line:
        raise _NoCommandError
    raw = json.loads(line)
    argv = [str(arg) for arg in raw["argv"]]
    if not argv:
        raise ValueError("exec request names an empty argv")
    env = {str(name): str(value) for name, value in raw["env"].items()}
    port = raw["bridge_port"]
    return argv, env, None if port is None else int(port), int(raw["bridge_limit"])


def _listen(port: int) -> list[socket.socket]:
    """Listen on `127.0.0.1:<port>`, and on `[::1]:<port>` where the jail's namespace has IPv6
    (decision-0009 item 1; where it has not, IPv4 alone, as the decision states). Called before
    the command starts, so the port is the bridge's before any program of the jail's could take
    it. Each socket is close-on-exec, as Python makes every socket, so the command inherits none.
    An `OSError` binding `127.0.0.1:<port>` propagates.
    """
    listeners = [socket.create_server(("127.0.0.1", port), backlog=128)]
    try:
        listeners.append(
            socket.create_server(
                ("::1", port), family=socket.AF_INET6, backlog=128, dualstack_ipv6=False
            )
        )
    except OSError:
        pass
    return listeners


def _copy(source: socket.socket, sink: socket.socket) -> None:
    """Copy bytes from `source` to `sink` until `source` ends, then end `sink`'s writing half.
    An error on either ends both whole, so the copy the other way stops too. Bytes only: the
    supervisor reads nothing the command sends."""
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


def _relay(accepted: socket.socket, kept: socket.socket, slots: threading.Semaphore) -> None:
    """Relay `accepted` (the command's connection) and `kept` (this side of its socketpair to
    the proxy) both ways until each has ended, then close both and give back the connection's
    slot. A copy thread that cannot start ends both at once."""
    try:
        back = threading.Thread(target=_copy, args=(kept, accepted), daemon=True)
        try:
            back.start()
        except RuntimeError:
            return
        _copy(accepted, kept)
        back.join()
    finally:
        accepted.close()
        kept.close()
        slots.release()


def _bridge_one(proxy: socket.socket, accepted: socket.socket, slots: threading.Semaphore) -> None:
    """Hand one accepted connection, which holds one of `slots`, to the proxy: a socketpair, one
    end sent over `proxy` with `SCM_RIGHTS` and closed here, the other relayed with `accepted`.
    A proxy that cannot take it (gone, or its end full and closed), or a relay thread that
    cannot start, closes `accepted` and gives the slot back: the connection fails, never routes
    elsewhere."""
    handed, kept = socket.socketpair()
    try:
        socket.send_fds(proxy, [b"c"], [handed.fileno()])
    except OSError:
        accepted.close()
        kept.close()
        slots.release()
        return
    finally:
        handed.close()
    try:
        threading.Thread(target=_relay, args=(accepted, kept, slots), daemon=True).start()
    except RuntimeError:
        accepted.close()
        kept.close()
        slots.release()


def _accept(listener: socket.socket, proxy: socket.socket, slots: threading.Semaphore) -> None:
    """Accept on `listener` for the supervisor's life, bridging each connection to `proxy` while
    one of `slots` is free; one more is closed as soon as it is accepted."""
    while True:
        try:
            accepted, _ = listener.accept()
        except OSError:
            continue
        if not slots.acquire(blocking=False):
            accepted.close()
            continue
        _bridge_one(proxy, accepted, slots)


def _start_bridge(listeners: list[socket.socket], limit: int) -> None:
    """Accept on each of `listeners` on a daemon thread of its own, bridging to the proxy over
    `_BRIDGE_FD` at most `limit` connections at once across them all: the jail's. Started only
    once the command exists, so `posix_spawnp` ran with one thread; daemon, so the supervisor's
    exit after `done` ends them, and every socket with it."""
    proxy = socket.socket(fileno=_BRIDGE_FD)
    slots = threading.BoundedSemaphore(limit)
    for listener in listeners:
        threading.Thread(target=_accept, args=(listener, proxy, slots), daemon=True).start()


def _emit(message: dict[str, object]) -> None:
    """Write one event line to `_EVENTS_FD` with one unbuffered `os.write` (the supervisor's
    wire, the one write path rule 14 allows here)."""
    os.write(_EVENTS_FD, (json.dumps(message) + "\n").encode())


def _start_child(argv: list[str], env: dict[str, str], bridged: bool = False) -> int:
    """Start `argv` in `env` as this process's child, with `posix_spawnp` (no Python after a
    fork), and return its pid.

    The child inherits fd 0, 1 and 2, and `_REQUEST_FD` and `_EVENTS_FD` are closed in it: a
    command holding `_EVENTS_FD` could write a `done` of its own and make `run_jail` report its
    exit code while it ran on (measured, TASK-0001.15/.17;
    `test_supervisor_link_gateway.py` plants it). Both must still be open here, since a `CLOSE`
    on a closed fd fails the spawn with `EBADF`. The closes are not enough alone: the command
    could reopen them through `/proc/1/fd` while this process is dumpable, which
    `_make_undumpable` prevents (TASK-0022). With `bridged`, `_BRIDGE_FD` is closed in it the
    same way: the command reaches the proxy only through the bridge's port.
    """
    closed = (_REQUEST_FD, _EVENTS_FD, _BRIDGE_FD) if bridged else (_REQUEST_FD, _EVENTS_FD)
    return os.posix_spawnp(
        argv[0],
        argv,
        env,
        file_actions=[(os.POSIX_SPAWN_CLOSE, fd) for fd in closed],
    )


def _forward_signal(child_pid: int, sig: int, frame: FrameType | None) -> None:
    """Forward a signal to the started child. PID 1 of a namespace ignores every signal it has
    no handler for (`pid_namespaces(7)`), so without this teardown's TERM would do nothing.
    Installed for `SIGTERM` and `SIGINT` (TASK-0020); KILL needs none."""
    del frame
    try:
        os.kill(child_pid, sig)
    except ProcessLookupError:
        pass


def _reap_until_gone(child_pid: int) -> int:
    """Reap every child, `child_pid` and each orphan reparented here, until none remain, emit
    `exited` for `child_pid` only, and return its exit code.

    Raises:
        ChildProcessError: no children were left before `child_pid` was reaped; it should not
            happen, and is reported rather than guessed past.
    """
    child_exit_code: int | None = None
    while True:
        try:
            reaped_pid, status = os.waitpid(-1, 0)
        except ChildProcessError:
            if child_exit_code is None:
                raise
            return child_exit_code
        exit_code = os.waitstatus_to_exitcode(status)
        if reaped_pid == child_pid:
            child_exit_code = exit_code
            _emit({"kind": "exited", "pid": reaped_pid, "exit_code": exit_code})


def _main() -> None:
    """Run the supervisor's one journey: make this process unreachable from the command, take
    `SIGTERM`/`SIGINT` before anything else, read the exec request, start the command (forwarding
    any signal that came first), report it started, reap until nothing remains, report it done.

    The handlers go in first because a PID 1 drops, at send time, any signal it has no handler
    for, blocked or not (TASK-0030): a `SIGINT` sent before the command existed was lost while
    the host was told it had been delivered. One that arrives before the command exists is held
    and forwarded as soon as it does.

    With a bridge port, the loopback listeners are bound before the command starts and accept
    once it has (`_listen`, `_start_bridge`); a port that cannot be bound ends the supervisor
    before the command exists, so nothing runs with a route the host did not see made.
    """
    _make_undumpable()
    started: list[int] = []
    held: list[int] = []

    def forward(sig: int, frame: FrameType | None) -> None:
        if started:
            _forward_signal(started[0], sig, frame)
        else:
            held.append(sig)

    for forwarded in (signal.SIGTERM, signal.SIGINT):
        signal.signal(forwarded, forward)
    argv, env, bridge_port, bridge_limit = _read_exec_request()
    listeners = _listen(bridge_port) if bridge_port is not None else []
    child_pid = _start_child(argv, env, bridged=bridge_port is not None)
    started.append(child_pid)
    for sig in held:
        _forward_signal(child_pid, sig, None)
    # Only now: `_start_child`'s CLOSE action needed it open (`_read_exec_request`).
    os.close(_REQUEST_FD)
    if listeners:
        _start_bridge(listeners, bridge_limit)
    _emit({"kind": "started", "pid": child_pid})
    exit_code = _reap_until_gone(child_pid)
    _emit({"kind": "done", "exit_code": exit_code})


if __name__ == "__main__":
    _main()
