"""The supervisor: PID 1 inside the jail's namespace (decision-0002).

Reads one `exec` request from fd 3, starts the command as its child, reaps everything
reparented to it (nothing else in the namespace will), and writes `started`, `exited` and
`done` to fd 4. Assembled with `wire.py` into one stdlib-only file (rule 17), where an import of
`wire` cannot resolve, so it repeats `wire.py`'s numbers and message shapes.
"""

import ctypes
import json
import os
import signal
from types import FrameType

_REQUEST_FD = 3
"""`wire.REQUEST_FD`, repeated."""

_EVENTS_FD = 4
"""`wire.EVENTS_FD`, repeated."""


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


def _read_exec_request() -> tuple[list[str], dict[str, str]]:
    """Read and parse the one exec request on `_REQUEST_FD`.

    Leaves `_REQUEST_FD` open (`closefd=False`): `_start_child`'s `CLOSE` action names it, and
    `posix_spawn` fails the whole spawn with `EBADF` for a `CLOSE` on a fd that is not open
    (measured). `_main` closes it after the spawn.

    Raises:
        _NoCommandError: `_REQUEST_FD` closed (EOF) before a line arrived.
        ValueError: the line read is not well-formed JSON, is missing
            `argv` or `env`, or names an empty `argv`.
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
    return argv, env


def _emit(message: dict[str, object]) -> None:
    """Write one event line to `_EVENTS_FD` with one unbuffered `os.write` (the supervisor's
    wire, the one write path rule 14 allows here)."""
    os.write(_EVENTS_FD, (json.dumps(message) + "\n").encode())


def _start_child(argv: list[str], env: dict[str, str]) -> int:
    """Start `argv` in `env` as this process's child, with `posix_spawnp` (no Python after a
    fork), and return its pid.

    The child inherits fd 0, 1 and 2, and `_REQUEST_FD` and `_EVENTS_FD` are closed in it: a
    command holding `_EVENTS_FD` could write a `done` of its own and make `run_jail` report its
    exit code while it ran on (measured, TASK-0001.15/.17;
    `test_supervisor_link_gateway.py` plants it). Both must still be open here, since a `CLOSE`
    on a closed fd fails the spawn with `EBADF`. The closes are not enough alone: the command
    could reopen them through `/proc/1/fd` while this process is dumpable, which
    `_make_undumpable` prevents (TASK-0022).
    """
    return os.posix_spawnp(
        argv[0],
        argv,
        env,
        file_actions=[
            (os.POSIX_SPAWN_CLOSE, _REQUEST_FD),
            (os.POSIX_SPAWN_CLOSE, _EVENTS_FD),
        ],
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
    argv, env = _read_exec_request()
    child_pid = _start_child(argv, env)
    started.append(child_pid)
    for sig in held:
        _forward_signal(child_pid, sig, None)
    # Only now: `_start_child`'s CLOSE action needed it open (`_read_exec_request`).
    os.close(_REQUEST_FD)
    _emit({"kind": "started", "pid": child_pid})
    exit_code = _reap_until_gone(child_pid)
    _emit({"kind": "done", "exit_code": exit_code})


if __name__ == "__main__":
    _main()
