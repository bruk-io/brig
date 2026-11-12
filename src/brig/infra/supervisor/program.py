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
import sys
import threading
from types import FrameType

_REQUEST_FD = 3
"""`wire.REQUEST_FD`, repeated."""

_EVENTS_FD = 4
"""`wire.EVENTS_FD`, repeated."""

_BRIDGE_FD = 5
"""`wire.BRIDGE_FD`, repeated."""

_BRIDGE_LISTENER_FDS = (6, 7)
"""`wire.BRIDGE_LISTENER_FDS`, repeated."""

_RELAY_CHUNK = 65536
"""How many bytes one bridged read takes at most."""


_PR_SET_DUMPABLE = 4
"""`prctl(2)`'s option number for the dumpable flag (`<linux/prctl.h>`): `ctypes` has no name
for it, and the standard library has no `prctl` of its own."""

_PT_DENY_ATTACH = 31
"""`ptrace(2)`'s request number on Darwin (`<sys/ptrace.h>`): blocks any process from attaching
to this process via `ptrace` or Mach task ports (decision-0010 item 2)."""


class _NoCommandError(Exception):
    """Raised when `_REQUEST_FD` closes before one `exec` request line arrives."""

    def __init__(self) -> None:
        super().__init__(f"fd {_REQUEST_FD} closed before an exec request arrived")


class _NotProtectedError(Exception):
    """Raised when this process cannot make itself non-dumpable, so the command would be able
    to reach it (decision-0006): the supervisor refuses to start the command at all."""


def _make_undumpable() -> None:
    """Make this process non-dumpable before the command exists (decision-0006 item 1,
    decision-0010 item 2).

    The command is this process's child, under the same uid: on Linux it has the jail's own
    procfs, so while this process is dumpable the command can reopen `_EVENTS_FD` through
    `/proc/1/fd/4` and write a `done` of its own, whatever `_start_child`'s closes did, and
    `ptrace` this process outright. Non-dumpable, both are refused to a peer without
    `CAP_SYS_PTRACE` in the jail's user namespace, which `--cap-drop ALL` (the bwrap
    compile) ensures the command never holds. On Darwin (`/proc` absent), `PT_DENY_ATTACH`
    refuses `ptrace` attachment from any child process. The command's own exec resets the
    flag for the child, which protects nothing of brig's.

    Raises:
        _NotProtectedError: `prctl` or `ptrace` refused the flag.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        libc.ptrace.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        libc.ptrace.restype = ctypes.c_int
        if libc.ptrace(_PT_DENY_ATTACH, 0, ctypes.c_void_p(0), 0) != 0:
            raise _NotProtectedError(
                f"ptrace(PT_DENY_ATTACH) failed: {os.strerror(ctypes.get_errno())}"
            )
        return
    if libc.prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise _NotProtectedError(
            f"prctl(PR_SET_DUMPABLE, 0) failed: {os.strerror(ctypes.get_errno())}"
        )


def _read_exec_request() -> tuple[list[str], dict[str, str], int | None, int, bool]:
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
    inherited = bool(raw.get("bridge_inherited", False))
    return argv, env, None if port is None else int(port), int(raw["bridge_limit"]), inherited


def _keep_listeners_from_children() -> None:
    """Make each of `_BRIDGE_LISTENER_FDS` that the host passed in close-on-exec, first thing,
    so neither the freezer nor the command, nor anything they start, inherits a listener and
    accepts on the bridge's port. An fd that is not open is left alone."""
    for fd in _BRIDGE_LISTENER_FDS:
        try:
            os.set_inheritable(fd, False)
        except OSError:
            pass


def _inherited_listeners() -> list[socket.socket]:
    """The bridge's listeners the host bound and passed as `_BRIDGE_LISTENER_FDS`
    (`bridge_inherited`): a Seatbelt jail's, whose profile lets nothing in it bind
    (decision-0010 item 4). An `OSError` from a listener fd that is not open, or not a
    socket, propagates: the supervisor ends before the command starts.
    """
    return [socket.socket(fileno=fd) for fd in _BRIDGE_LISTENER_FDS]


def _listen(port: int) -> list[socket.socket]:
    """Listen on `127.0.0.1:<port>`, and on `[::1]:<port>` where the jail's namespace has IPv6
    (decision-0009 item 1; where it has not, IPv4 alone, as the decision states). Called before
    the command starts, so the port is the bridge's before any program of the jail's could take
    it. Each socket is close-on-exec, as Python makes every socket, so the command inherits none.

    On Darwin the jail shares the host's network stack and its profile lets the command reach
    the port on every local address, `[::1]` included (measured, decision-0010 item 4), so a
    `[::1]:<port>` this cannot take would be some host program's, reached past the proxy.

    Raises:
        OSError: `127.0.0.1:<port>` could not be bound, or, on Darwin, `[::1]:<port>`; the jail
            never starts.
    """
    listeners = [socket.create_server(("127.0.0.1", port), backlog=128)]
    try:
        listeners.append(
            socket.create_server(
                ("::1", port), family=socket.AF_INET6, backlog=128, dualstack_ipv6=False
            )
        )
    except OSError:
        if sys.platform == "darwin":
            raise
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


_FREEZER_MARKER = "brig-teardown-freezer"
"""`infra.members.FREEZER_MARKER`, repeated: this file is assembled without brig."""

FREEZER_FLAG = "--freezer"
"""The argument the Seatbelt launch gives this program, after its own path, to start the freezer:
nothing else starts it, so a supervisor run outside a Seatbelt jail (bwrap's, a test's) never
does."""

_FREEZER = """
import ctypes, os, signal, sys
signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1})
libsystem = ctypes.CDLL("/usr/lib/libSystem.dylib")
libsystem.sandbox_check.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
libsystem.sandbox_check.restype = ctypes.c_int
if libsystem.sandbox_check(os.getpid(), None, 0) != 1:
    os._exit(0)
try:
    os.kill(int(sys.argv[2]), 0)
except PermissionError:
    pass
except (OSError, IndexError, ValueError):
    os._exit(0)
else:
    os._exit(0)
if os.fork():
    os._exit(0)
os.setsid()


def freeze(signum, frame):
    while True:
        os.kill(-1, signal.SIGSTOP)


signal.signal(signal.SIGUSR1, freeze)
signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGUSR1})
while True:
    signal.pause()
"""
"""The jail's teardown freezer on Darwin (decision-0010 item 2): it forks away from the supervisor
and leads a session of its own, so it outlives its command and the supervisor, holds none of
their pipes, and is neither reaped nor waited on as their child. Told with `SIGUSR1`, it stops
every process of its sandbox, itself included, with `kill(-1, SIGSTOP)`, and again each time
the host continues it, until the host has seen the whole jail stopped and killed it
(`infra.members.freeze_and_kill`). `SIGUSR1` is blocked until its handler is in, so one sent
early is held, not fatal. Outside a sandbox `kill(-1, SIGSTOP)` would stop every process of
the user, so it exits at once unless `sandbox_check` says it is sandboxed (with no filter, the
call takes no variadic argument), and unless a signal to the host that started the jail, whose
pid it is given, is refused (`EPERM`): that checks the signal's reach itself, not only that some
sandbox is there, so a sandbox whose signals reach outside it never arms one."""


def _is_open(fd: int) -> bool:
    """Whether `fd` is open in this process."""
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def _start_freezer() -> None:
    """Start the teardown freezer (`_FREEZER`) on Darwin when the launch asks for it
    (`FREEZER_FLAG`), before the command exists, given the host's pid (this process's parent:
    the host spawns `sandbox-exec`, which execs this program in place): stdio on
    `/dev/null`, none of the supervisor's own fds (the bridge's included, when it has one). A
    no-op elsewhere, where the jail's PID namespace ends every process of the jail with its PID
    1. An `OSError` from the spawn propagates: the supervisor ends before the command starts.
    """
    if sys.platform != "darwin" or FREEZER_FLAG not in sys.argv[1:]:
        return
    held = [fd for fd in (_REQUEST_FD, _EVENTS_FD, _BRIDGE_FD) if _is_open(fd)]
    actions: list[tuple[int, ...] | tuple[int, int, str, int, int]] = [
        (os.POSIX_SPAWN_OPEN, fd, "/dev/null", os.O_RDWR, 0) for fd in (0, 1, 2)
    ]
    actions += [(os.POSIX_SPAWN_CLOSE, fd) for fd in held]
    os.posix_spawn(
        sys.executable,
        [sys.executable, "-I", "-c", _FREEZER, _FREEZER_MARKER, str(os.getppid())],
        {},
        file_actions=actions,
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
    _keep_listeners_from_children()
    started: list[int] = []
    held: list[int] = []

    def forward(sig: int, frame: FrameType | None) -> None:
        if started:
            _forward_signal(started[0], sig, frame)
        else:
            held.append(sig)

    for forwarded in (signal.SIGTERM, signal.SIGINT):
        signal.signal(forwarded, forward)
    _start_freezer()
    argv, env, bridge_port, bridge_limit, inherited = _read_exec_request()
    if bridge_port is None:
        listeners: list[socket.socket] = []
    elif inherited:
        listeners = _inherited_listeners()
    else:
        listeners = _listen(bridge_port)
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
