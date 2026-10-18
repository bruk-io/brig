"""The supervisor itself: PID 1 inside the jail's own namespace.

decision-0002's minimal first version: reads one `exec` request from its own
fd `3` (the real command to run, and its environment), forks that command as
its own child, reaps everything reparented to it afterward -- the child itself
and every orphan an exiting process inside the namespace leaves behind,
since nothing else inside the namespace will ever reap them once this
process is PID 1 there -- and reports `started`/`exited`/`done` back over its
own fd `4`, one newline-delimited JSON line each.

DRAFT-0010's resolution: the wire protocol travels on fd `3`/`4`
(`_REQUEST_FD`/`_EVENTS_FD` below), never fd `0`/`1`/`2` -- `infra/supervisor/
link.py`'s `_start` dup2s the two pipes there instead, by name, and leaves
this process's own fd `0`/`1`/`2` to inherit from the host exactly as they
would with no supervisor in between. That is what lets `_start_child` give
the real command below its *own* stdio again -- inherited unchanged, not a
sealed pipe standing in for it -- while still explicitly closing `3`/`4` in
that same spawn so the real command can never reach the wire channel itself,
the same authentication-hole reasoning that previously sealed `0`/`1`, now
aimed at the two numbers the channel actually lives on.

Deliberately duplicates `wire.py`'s trivial JSON encode/decode rather than
importing it (`_emit`, `_read_exec_request` below): this module and `wire.py`
assemble into the one stdlib-only file dropped as PID 1 inside the jail
(decision-0001 rule 17), and a plain `import wire` -- the only form that
would resolve once these two are the only two files present with no `brig`
package installed around them -- is not resolvable from *this* file's own
location inside the `brig.infra.supervisor` package during ordinary
development, type-checking or `pypeeker check`: it would need a second,
unqualified top-level module named `wire` nothing here declares. Importing
it as `brig.infra.supervisor.wire` instead would commit this module to brig
being installed wherever it runs, exactly what the assembled, dropped file
must not depend on. Stdlib only, no import of anything else under `brig`.
`link.py` is the host's end of the same protocol, in the library's own
process, where importing `wire.py` normally costs nothing -- confirmed in
TASK-0001.15 step 3 (DRAFT-0009 AC#3): `link.py` imports
`wire.encode_exec_request` and `wire.decode_event` directly -- so the shared
format lives once, in `wire.py`, with this module's own encoding kept in
exact agreement with it by convention (the literal `kind`/field names below
match `wire.py`'s `MessageKind` members and TypedDict fields one for one)
rather than by import, and by whatever test a later step of TASK-0001.15
adds to pin that agreement.

Every name below is leading-underscore: nothing outside this module calls
any of them (not even `link.py`, since starting the assembled file is a
subprocess call, not an import), the same reasoning `wire.py`'s own
docstring gives for its names.
"""

import json
import os
import signal
from types import FrameType

_REQUEST_FD = 3
"""Duplicates `wire.py`'s own `REQUEST_FD`, by value, for the same reason this
module's own docstring already gives for duplicating its message shapes: this
module cannot import `wire.py` once assembled alongside it into the one file
dropped as PID 1. Kept in exact agreement with it by this same convention,
not by import.
"""

_EVENTS_FD = 4
"""Duplicates `wire.py`'s own `EVENTS_FD`, by value -- see `_REQUEST_FD`."""


class _NoCommandError(Exception):
    """Raised when `_REQUEST_FD` closes before one `exec` request line arrives."""

    def __init__(self) -> None:
        super().__init__(f"fd {_REQUEST_FD} closed before an exec request arrived")


def _read_exec_request() -> tuple[list[str], dict[str, str]]:
    """Read and parse the one line `_REQUEST_FD` carries before anything is
    forked: `{"kind": "exec", "argv": [...], "env": {...}}` (`wire.py`'s
    `_ExecRequest`, encoded independently here -- see this module's own
    docstring for why).

    Opens `_REQUEST_FD` as a buffered text file only for the one `readline()`
    this needs, with `closefd=False`: the wrapper itself is released once this
    function returns, but `_REQUEST_FD` stays open in this process a little
    longer, since `_start_child`'s own `file_actions` -- run immediately
    after this, from `_main` -- still names it (to close *the real command's*
    copy, never this process's own). Measured, not assumed: `os.posix_spawn`'s
    `CLOSE` file action on a fd that is not open at all fails the *whole*
    spawn with `EBADF`, the same way a bad `argv[0]` does -- closing
    `_REQUEST_FD` here, before that action ever runs, would make every
    supervised command fail to start. `_main` closes this process's own copy
    once `_start_child` has returned -- there is nothing left to say on it
    afterward (the protocol sends exactly one exec request, ever, `wire.py`'s
    own docstring), but not a moment sooner.

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
    """Write one newline-delimited JSON event line to `_EVENTS_FD`, so the host
    sees each event as it happens -- this is the supervisor's own wire, the
    one write path decision-0001 rule 14 carves out alongside `infra/log.py`.

    A plain `os.write`, not a buffered file object: `_EVENTS_FD` carries only
    this process's own event stream for its entire lifetime (unlike
    `_REQUEST_FD`, read once and closed), so there is no second buffering
    layer here to flush or forget to flush -- every write lands immediately,
    the same guarantee the sealed-pipe-era `sys.stdout.flush()` existed to
    give, with nothing to defeat it this time.
    """
    os.write(_EVENTS_FD, (json.dumps(message) + "\n").encode())


def _start_child(argv: list[str], env: dict[str, str]) -> int:
    """Start `argv` as this process's own child, running in `env`, and
    return its pid.

    `os.posix_spawnp`, the same mechanism `infra/processes.py`'s `spawn`
    uses on the host side and for the same reason its docstring gives: the
    fork and the exec both happen inside the platform's C library, never as
    Python bytecode running after a fork, so nothing async-signal-unsafe can
    deadlock this process -- which matters here even though this process is
    single-threaded, since it is the one thing standing in for PID 1 for
    everything else inside the jail's namespace, and must not be the thing
    that hangs it.

    Leaves `argv`'s fd 0/1/2 alone -- no file action for any of them -- so
    `argv` inherits this process's own fd 0/1/2 exactly as it would with no
    supervisor in between (DRAFT-0010's resolution: this process's own fd
    0/1/2 are never the wire protocol any more, `link.py`'s `_start`
    connects that to fd `_REQUEST_FD`/`_EVENTS_FD` instead -- see this
    module's own docstring). Explicitly closes `_REQUEST_FD` and
    `_EVENTS_FD` for `argv`, the one thing that *does* need stating: both
    numbers are still open and still inheritable *in this process* at the
    point this runs, and `os.posix_spawnp` inherits every fd that is both
    of those unless a file action says otherwise -- without this, `argv`
    would inherit `_EVENTS_FD` as a fd of its own and could write a forged
    `started`/`exited`/`done` line directly onto the channel the host
    trusts. This is a real, load-bearing ordering requirement, not an
    incidental one: `_REQUEST_FD` is open here specifically because
    `_main` calls this function *before* closing its own copy of it (see
    `_read_exec_request`'s own docstring for why), and `_EVENTS_FD` is open
    for this process's entire remaining life regardless. `os.posix_spawnp`'s
    `CLOSE` file action on a fd that is *not* open fails the whole spawn
    outright with `EBADF` (measured, not assumed, while building this fix) --
    so this function's own two `CLOSE` actions depend on `_main` still
    calling it before `_REQUEST_FD` closes, the same way they depend on
    `_EVENTS_FD` never having closed at all; reordering `_main` without
    keeping that true breaks every supervised command's spawn, not only an
    adversarial one.

    Without the two `CLOSE` actions below, `argv` could write a forged
    `started`/`exited`/`done` line directly onto the channel the host
    trusts -- the exact confused-deputy hole TASK-0001.15/.17's adversarial
    review found and a since-removed sealed pipe once closed at fd 1
    instead, reopened here at fd `_EVENTS_FD` if this one line were ever
    dropped (regression coverage: `tests/e2e/test_supervisor_link_gateway.py`'s
    `..._direct_write_to_the_events_fd_cannot_reach_it`, which writes to
    `wire.EVENTS_FD` by number rather than through fd 1, specifically so
    deleting these two actions fails it). Measured then, unforgotten now: a
    command that writes `{"kind": "done", "exit_code": 0}\\n` onto a fd the
    host reads events from makes the host's `run_jail` return that
    fabricated exit code and forget the real process entirely, while the
    real command keeps running arbitrarily long afterward -- the exit code
    the host trusts stops being `waitpid(2)`-authenticated (unforgeable by
    the confined process) and becomes whatever the confined process
    chooses to write to a channel it was never supposed to reach.
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
    """Forward a signal this process receives to its one started child.

    A process acting as PID 1 inside its own PID namespace has every
    signal's disposition it does not explicitly handle forced to the
    kernel's default-ignore for an init process, regardless of what that
    signal would ordinarily do to an unrelated process (measured: Linux
    `pid_namespaces(7)`) -- without a handler installed here, decision-0002's
    teardown ladder's TERM rung would reach this process and do nothing, and
    only the later KILL rung (which no process can ignore) would ever act.
    Installed for `SIGTERM` only; `SignalGroup`'s `KILL` already bypasses
    this process entirely; see `_main`.
    """
    del frame
    try:
        os.kill(child_pid, sig)
    except ProcessLookupError:
        pass


def _reap_until_gone(child_pid: int) -> int:
    """Reap every process reparented to this one as PID 1 -- the started
    child and every orphan reparented to it afterward -- until none remain,
    and return the started child's own exit code.

    Loops a blocking `os.waitpid(-1, 0)`, which waits on *any* child of this
    process, not only `child_pid`: that is what "reaps everything
    reparented to it, including orphans" (decision-0002) means for the one
    process acting as PID 1 inside the jail's namespace. An orphan's
    original parent exiting inside the namespace reparents it to this
    process, and nothing else inside the namespace will ever reap it if
    this loop does not. Only `child_pid`'s own exit is reported outward (an
    `exited` event, emitted here as soon as it is seen) -- every other pid
    this reaps is an orphan this process owes no event to, since the host
    never asked about it; reaping it without reporting it is still
    necessary, so it does not sit as a zombie until this loop ends.

    Returns:
        The exit code `os.waitstatus_to_exitcode` reports for `child_pid`.

    Raises:
        ChildProcessError: this process ran out of children to wait for
            (`ECHILD`) before `child_pid` -- its own direct child -- was
            ever among them. Nothing else inside this namespace can reap a
            child of this single process, so this should never happen; it
            is reported rather than guessed past.
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
    """Run the supervisor's one journey: read the exec request, start the
    command, report it started, reap until nothing remains, report it done.
    """
    argv, env = _read_exec_request()
    child_pid = _start_child(argv, env)
    # `_read_exec_request`'s own docstring explains why this process's own
    # `_REQUEST_FD` had to stay open past that call -- `_start_child`'s file
    # actions, just run, needed it there to close *the real command's* copy.
    # Nothing here has a further use for it.
    os.close(_REQUEST_FD)
    _emit({"kind": "started", "pid": child_pid})
    signal.signal(signal.SIGTERM, lambda sig, frame: _forward_signal(child_pid, sig, frame))
    exit_code = _reap_until_gone(child_pid)
    _emit({"kind": "done", "exit_code": exit_code})


if __name__ == "__main__":
    _main()
