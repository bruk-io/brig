"""`link.py`: the host's end of the supervisor's wire protocol (decision-0002).

Starts the file `wire.py` and `program.py` assemble into -- dropped as PID 1 inside
the jail's own namespace, by whatever argv a jail type's driver built to get it
running there (TASK-0001.15 step 4's own wiring, `presentation/api.py`; this module
is jail-type-agnostic and takes that argv as given) -- as this process's own child,
through `infra.processes.spawn` rather than a `posix_spawn` call of its own: every
hardening `spawn` already carries (the `setsid`/`setpgroup` fallback, the `EBADF`
close-action retry, TASK-0001.08/.09) covers the supervisor's own start the same as
it does any other process this program starts.

Speaks the wire protocol `wire.py` names, imported directly rather than duplicated
(DRAFT-0009 AC#3, settled empirically here): this module never crosses into the jail
-- it runs in the library's own process, on this side of the boundary (decision-0002)
-- so a plain `from brig.infra.supervisor import wire` costs nothing, unlike
`program.py`'s own docstring explanation for why *it* cannot do the same. The direct
import works cleanly -- `just gates` is the evidence, not a guess -- once the four
names this module's own code actually calls (`Event`, `encode_exec_request`,
`decode_event`, and now `done_exit_code`/`WireError`, TASK-0001.15 step 4) dropped
their leading underscore: decision-0001 rule 6's `under-exposed-access` bans reaching
into another module's `_name`s, and `over-exposed-module-symbol` bans a public name
with no caller outside its own module, so this module existing and calling in is
exactly what changed the answer for those names. `wire.py`'s `MessageKind` stays
private still -- see its own docstring.

This module is `infra/`: it imports nothing from `brig.domain` or `brig.presentation`
(decision-0001 rule 1) and hands back plain data only -- `presentation/drivers/<type>.py`
is the one place that translates this module's own values into a domain effect's own
shape, through `presentation/ports.py`'s `SupervisorPort`.

`LiveSupervisors` is this module's one stateful class (decision-0001 rule 7: "a class
holding changing state only in infra/", its invariant in its own docstring below) --
the real `SupervisorPort` `presentation/api.py` wires in by default. It exists because
`presentation/ports.py`'s `SupervisorPort.await_done`/`close` take only the pid
`start` handed back (the one thing a `Process` carries between `operations.create()`'s
and `operations.start()`'s separate driver calls, decision-0002), never the open
`Supervisor` object itself -- something has to remember which `Supervisor` a pid
still names, between those two calls, and rule 7 says that something lives here, not
in `presentation/api.py`.

`_start` no longer hands one `env` mapping to both sides of the spawn it performs
(corrected here, TASK-0001.15/.17 adversarial review): the supervisor process itself
-- and `supervisor_argv[0]` ("bwrap", resolved by `posix_spawnp` through `PATH`,
running on the host before anything unshares) -- gets `_SUPERVISOR_ENV`, a fixed,
minimal, non-secret mapping, never the embedder's own `EnvPolicy`-scrubbed allow-list
meant for the *supervised command* (`domain/policy/env.py`'s own docstring: "which
environment variables a jail's supervised command may see"). Measured why the two
cannot share one mapping: an `EnvPolicy(allowed=("PYTHONPATH",))` the embedder stated
only to let the confined command see its own `PYTHONPATH` also, until this fix, let
an attacker-controlled `PYTHONPATH` run arbitrary code (a `sitecustomize.py`) inside
the supervisor's own interpreter the moment it started -- the process that becomes
PID 1 inside the jail and owns the host's control pipe, exactly the trust boundary
`_start` itself crosses -- and an attacker-controlled `LD_PRELOAD` reached `bwrap` on
the host, before any namespace existed to contain it. The allow-list states what the
confined process may see; it was never meant to state what the process enforcing the
confinement runs with, and the two sit on opposite sides of this module's own trust
boundary.

Measured why "this process's own environment" (`processes.spawn`'s own default,
`env` simply left unset) is *also* not safe here, a second, separate finding past the
one above: `WHOLE_HOST_READ_ONLY`'s own whole-host bind makes a real jail's `/proc`
reachable from inside it, and the supervised command -- the supervisor's own direct
child -- is always permitted to read `/proc/<supervisor's pid>/environ` regardless
of any fd this module closes (same uid, parent/child; no fd-table change answers
this). An embedder's real secrets, sitting in this process's own environment for
reasons that have nothing to do with brig, would have been one `/proc` read away
from the very command they were never meant to reach. `_SUPERVISOR_ENV`'s own
docstring carries the rest; the broader question it does not answer --
`/proc`-based introspection of the supervisor by its own child in general, which
predates and outlives this one disclosure -- is `WHOLE_HOST_READ_ONLY`'s own, still
open (tracked as a draft, not fixed here).

`presentation/api.py` additionally runs the supervisor's own interpreter with `-I`
(isolated mode), so a `PYTHONPATH` surviving in `_SUPERVISOR_ENV` for some unrelated
reason still cannot reach the supervisor either -- belt and braces with the split
above, not a substitute for it: `-I` does nothing for `LD_PRELOAD`, which never goes
through the interpreter at all.
"""

import os
import select
import time
from collections.abc import Mapping
from dataclasses import dataclass

from brig.infra import processes
from brig.infra.supervisor import wire

_READ_CHUNK = 4096
"""How many bytes `Supervisor.read_event` asks the OS for per `os.read` -- generous
next to one newline-delimited JSON event line, so the ordinary case is one syscall.
"""

_SUPERVISOR_ENV: dict[str, str] = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
"""The *only* environment `_start` ever gives the supervisor process itself --
never this process's own full `os.environ`, and never `command_env`.

Correction (TASK-0014): this `PATH` does *not* resolve `supervisor_argv[0]`
("bwrap") the way an earlier version of this docstring claimed. `posix_spawnp`'s
own `PATH` search, measured directly against both Apple's libc and glibc,
consults the *calling* process's real `os.environ` for that search, never the
`env` argument handed to the new process (`infra/processes.py`'s `spawn`
docstring has the full measurement) -- `env` only becomes the new process's own
environment once exec has already succeeded. So "bwrap" is already resolved,
regardless of what `_SUPERVISOR_ENV` says, by the time this function runs; this
`PATH` entry exists only as a sane, minimal default for whatever bwrap's own
internals (or anything it in turn execs) might consult `PATH` for once running,
not to make the spawn itself succeed. Measured why "this process's own environment"
(an earlier version of this fix) was still not safe, even after `command_env` no
longer reached the supervisor's own spawn (TASK-0001.15/.16/.17 adversarial
review): `WHOLE_HOST_READ_ONLY`'s own whole-host bind makes a real jail's `/proc`
reachable from inside it, and a process can always read `/proc/<pid>/environ` of
another process it is permitted to introspect (same uid, parent/child -- the
supervised command's own relationship to the supervisor, regardless of any fd this
module closes) -- so whatever this process's own environment carried, including an
embedder's real secrets, was one `/proc` read away from the very command it was
meant to be kept from. A minimal, fixed, non-secret environment closes that
specific disclosure; it does not close `/proc`-based introspection in general,
which is this policy's own, separate, still-open question (tracked, not fixed,
here).
"""


class SupervisorSpawnError(Exception):
    """Raised when the supervisor process itself could not be started.

    Args:
        argv: The command that could not be run.
    """

    def __init__(self, argv: tuple[str, ...]) -> None:
        super().__init__(f"could not start the supervisor: {argv!r}")
        self.argv = argv


@dataclass(frozen=True)
class SupervisorDoneUnknown:
    """Sentinel `_await_one_done`/`LiveSupervisors.await_done` return in place of an
    exit code when the supervisor's report for this process can never be recovered
    now: the events pipe reached EOF with no `done` event ever having arrived, or a
    line read from it failed to decode at all (`wire.WireError`) or could not be read
    at all (`OSError`) -- any of the three leaves nothing further this supervisor can
    answer reliably, so all three fold into this one sentinel rather than raising
    (this is infra: it hands back plain data only, decision-0001 rules 1 and 9).

    Distinct from `None`, which `await_done` returns instead when `deadline` passes
    first with the supervisor simply not done yet: a later `await_done` call can
    still succeed there, unlike this one. Mirrored, not imported, by
    `presentation/ports.py`'s own sentinel of the same name, the way
    `infra.processes.ProcessUnknown` already mirrors into `ports.ProcessUnknown`
    (`ports.py`'s own module docstring) -- the real wiring (`presentation/api.py`)
    is the one place that translates this module's value into that one.
    """


@dataclass(frozen=True)
class ReadTimedOut:
    """Sentinel `Supervisor.read_event` returns in place of a `wire.Event` when
    `deadline` passes with a whole line not yet formed.

    Distinct from `None`, which `read_event` returns instead for a genuine EOF
    (the supervisor process itself has exited and closed its own `wire.EVENTS_FD`,
    with nothing left pending): a later `read_event` call with a fresh `deadline` can still
    succeed after this one, unlike after `None` (TASK-0001.15/.17 adversarial
    review: collapsing the two, the way the pre-fix code effectively did by never
    bounding the read at all, is exactly what let a deadline be defeated
    indefinitely -- the same "two outcomes a caller must not treat alike" reasoning
    `effects.ExitCodeUnknown`'s own docstring already gives for `Reap`, one layer
    lower). `self._pending` is left exactly as it was: whatever bytes already
    arrived stay buffered for that later call to resume, per `Supervisor`'s own
    invariant.
    """


class Supervisor:
    """A supervisor `_start` began: its process identity, and the still-open read
    end of the pipe its `started`/`exited`/`done` events arrive on.

    `pid` and `pgid` are set once, at `_start`, and read-only from here on -- a
    plain dataclass would hold those two alone. This carries one piece of changing
    state besides them, `_pending`: whatever bytes have arrived on `events_fd` and
    not yet formed one whole newline-delimited line. `os.read` can return less than
    one full line or more than one, so something must hold the remainder between
    calls either way (decision-0001 rule 7's "a class holding changing state... its
    invariant in its docstring" -- this is that invariant). `events_fd` itself
    stays open for as long as this value is in use; call `close` once this process
    will not call `read_event` again for it, since infra itself has no notion of
    "later" to close it on its own (rule 1: plain data in, plain data out).
    """

    def __init__(self, pid: int, pgid: int, events_fd: int) -> None:
        self.pid = pid
        self.pgid = pgid
        self.events_fd = events_fd
        self._pending = b""

    def read_event(self, deadline: float) -> wire.Event | None | ReadTimedOut:
        """Read and decode the next line `events_fd` carries, waiting only until a
        whole line arrives, the pipe reaches EOF, or `time.monotonic()` passes
        `deadline` -- never a bare blocking read once this method has been entered,
        which would let a line with no trailing newline block past `deadline`
        regardless of how long the caller only meant to wait (measured, by way of
        `_await_one_done`'s own now-corrected docstring: a supervised command that
        writes a partial line with no newline and then sleeps held `run_jail` well
        past its stated `timeout_s`, because the read loop that waited for the rest
        of that line was not itself bounded by anything).

        Bounds every wait on `events_fd` becoming readable with `select.select`
        against the time left before `deadline`, the same way `_await_one_done`
        used to bound only its own first wait; a `chunk` that arrives with no
        newline in it is appended to `self._pending` and the loop continues,
        re-checking `deadline` before the next `select.select` rather than reading
        again unconditionally.

        Returns `None` once EOF arrives (the supervisor process itself has exited
        and closed its own `wire.EVENTS_FD`) with no further line pending -- distinct from any
        `wire.Event`, `done` included, which can still be read back before this.
        Returns `ReadTimedOut` instead if `deadline` passes first with a line still
        not fully formed: `self._pending` keeps whatever bytes already arrived,
        exactly as the class's own invariant requires, so a later call with a fresh
        `deadline` resumes the same partial line rather than losing it -- distinct
        from `None`, which a caller must never retry past (this mirrors
        `effects.ExitCodeUnknown`'s own "distinct from `None`" reasoning, one layer
        lower, for exactly the same kind of caller mistake). A line that is not one
        of `wire.py`'s event shapes propagates whatever `wire.decode_event` itself
        raises for it (`wire.WireError`), undocumented again here (ruff's DOC501:
        nothing in this function's own body raises it).
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
        """Close this process's own end of `events_fd`.

        Call exactly once, after the last `read_event` call this process will ever
        make for this supervisor -- this value tracks no "already closed" state of
        its own to make a second call safe.

        Swallows `OSError` (`EBADF`, most plausibly: `events_fd` already closed by
        something else) rather than raising it: this is infra, which hands back
        plain data only and never raises (decision-0001 rules 1 and 9), the same
        reasoning `infra/processes.py`'s `signal_group` already gives for
        swallowing a signal attempt against an already-gone process group, and the
        one this method's own caller (`destroy_jail`, by way of
        `SupervisorPort.close`) needs to be able to call unconditionally, during
        teardown, without a driver standing between it and this call to translate
        an infra exception into a presentation one.
        """
        try:
            os.close(self.events_fd)
        except OSError:
            pass


def _start(
    supervisor_argv: tuple[str, ...],
    command_argv: tuple[str, ...],
    command_env: Mapping[str, str],
) -> Supervisor:
    """Start `supervisor_argv` as this process's own child, and hand it
    `command_argv`/`command_env` to run as *its* one child, over the wire protocol.

    Opens two pipes. The request pipe carries exactly one line out, encoded by
    `wire.encode_exec_request` -- the protocol sends exactly one exec request, ever
    (decision-0002) -- written here and then closed, on both ends, before this
    returns: there is nothing left to say on it afterward. The events pipe's read end
    is `Supervisor.events_fd`; its write end is closed here, in this process,
    immediately after the spawn -- holding it open on this side as well as the
    child's would leave that pipe's write side with two owners, so a `read_event`
    call that should see a clean EOF once the supervisor itself exits would instead
    block forever on this process's own copy.

    Both pipes' other ends become the new process's fd `wire.REQUEST_FD`/
    `wire.EVENTS_FD` through `infra.processes.spawn`'s `fds` -- never fd `0`/`1`
    (DRAFT-0010), and never by touching this process's own copies around the call,
    which `spawn` leaves exactly as they were. Names `(0, 1, 2)` as the supervisor's
    own `inheritable_fds`, deliberately not `()`: the supervisor's own standard
    streams are exactly what the supervised command it starts in turn (`program.py`'s
    `_start_child`) inherits unchanged, since that function gives it no file actions
    of its own for any of the three -- so this is what actually lets the supervised
    command see the embedder's real stdio again, the same three numbers it would
    have inherited with no supervisor in between at all. Nothing past those three:
    this process's other open, inheritable fds have no business reaching the
    supervisor any more than they would a jailed command run directly (`Spawn`'s
    own reasoning, `domain/effects.py`) -- `wire.REQUEST_FD`/`wire.EVENTS_FD`
    themselves reach the supervisor only through `fds`'s own dup2 actions below,
    never by also being named here.

    `command_env` is handed only to `wire.encode_exec_request` -- the environment the
    supervisor is told to run the supervised *command* in, already scrubbed by
    `operations.create`'s own `EnvPolicy` (`domain/policy/env.py`) by the time it
    reaches here. The supervisor process itself gets `_SUPERVISOR_ENV` instead (this
    module's own docstring explains why that is a fixed, minimal, non-secret mapping
    now, not simply "whatever this process's own environment happens to carry") --
    deliberately never `command_env` either way (a mapping an embedder scrubbed down
    to what the *confined* command may see is not safe to also hand to the process
    enforcing the confinement).

    Raises:
        SupervisorSpawnError: `supervisor_argv` could not be started, or started
            and then died (or otherwise closed its own `wire.REQUEST_FD`) before
            the one exec request could be written to it.
    """
    request_read_fd, request_write_fd = os.pipe()
    events_read_fd, events_write_fd = os.pipe()
    try:
        spawned = processes.spawn(
            supervisor_argv,
            (0, 1, 2),
            env=_SUPERVISOR_ENV,
            fds={wire.REQUEST_FD: request_read_fd, wire.EVENTS_FD: events_write_fd},
        )
    except (processes.SpawnError, OSError) as exc:
        for fd in (request_read_fd, request_write_fd, events_read_fd, events_write_fd):
            os.close(fd)
        raise SupervisorSpawnError(supervisor_argv) from exc
    os.close(request_read_fd)
    os.close(events_write_fd)
    try:
        with os.fdopen(request_write_fd, "w") as request_pipe:
            request_pipe.write(wire.encode_exec_request(command_argv, command_env))
    except OSError as exc:
        # The `with` block above already closed `request_write_fd` on its way out,
        # even though the write raised -- only `events_read_fd` is still this
        # process's to close, since no `Supervisor` exists yet to own it. The
        # supervisor itself is presumed gone (a write past a closed read end is
        # exactly what raises here), so its pid is reaped rather than left a
        # zombie nothing else will ever collect -- best-effort: a second `OSError`
        # from that reap (ECHILD, say) is swallowed, not escalated, since this
        # function is already failing for its own reason.
        os.close(events_read_fd)
        try:
            os.waitpid(spawned.pid, 0)
        except OSError:
            pass
        raise SupervisorSpawnError(supervisor_argv) from exc
    return Supervisor(pid=spawned.pid, pgid=spawned.pgid, events_fd=events_read_fd)


def _await_one_done(supervisor: Supervisor, deadline: float) -> int | None | SupervisorDoneUnknown:
    """Wait for `supervisor` to report its one supervised command done, giving up
    once `time.monotonic()` passes `deadline`.

    Reads events one at a time (`supervisor.read_event(deadline)`, by way of
    `wire.done_exit_code` to tell a `started`/`exited` event apart from the `done`
    one actually waited for). The bound against `deadline` lives inside
    `read_event` itself now, for every wait it makes, not only the first
    (corrected here, TASK-0001.15/.17 adversarial review: a version of this
    function that bounded only its own first `select.select`, then handed off to a
    `read_event` that blocked without any deadline of its own, let a supervised
    command defeat `deadline` indefinitely by writing a line with no trailing
    newline and then never finishing it -- measured, a 2-second `deadline` held
    open past 12 seconds). `read_event(deadline)` returning `ReadTimedOut` is this
    function's own signal to stop and return `None`; nothing here calls
    `select.select` a second time for the same thing.

    Returns:
        The supervised command's exit code, once a `done` event is read. `None` if
        `deadline` arrives first with no `done` event seen yet -- a later call can
        still succeed, the pipe is left open (and, inside it, `self._pending` keeps
        whatever partial line already arrived -- `Supervisor.read_event`'s own
        `ReadTimedOut` docstring). `SupervisorDoneUnknown` if the pipe reaches EOF
        with no `done` event ever seen, or a line fails to read (`OSError`) or
        decode (`wire.WireError`) -- either way nothing further read from this
        supervisor can answer reliably, so nothing here is retried.
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


class LiveSupervisors:
    """The real `presentation.ports.SupervisorPort`: starts and tracks every
    supervisor this process currently has running, keyed by its own pid.

    Decision-0001 rule 7's stateful class, confined to infra/: its invariant is that
    every pid in `_open` names a `Supervisor` whose `events_fd` is still open, until
    `await_done` sees it done (or gone for good) or `close` removes it -- `start`
    adds the entry `await_done`/`close` later look back up, since `presentation/api.py`
    passes this same instance to every one of a jail's `create`/`start`/`destroy`
    driver calls, and a `Process` only ever carries a pid/pgid between them
    (decision-0002), never the open pipe itself.
    """

    def __init__(self, supervisor_argv: tuple[str, ...]) -> None:
        """`supervisor_argv` is the jail type's own bwrap-wrapped (or equivalent)
        launch line for the supervisor's file -- fixed for the lifetime of this
        instance, computed once by whoever wires this in (`presentation/api.py`),
        never varying per `start` call the way the supervised command itself does.
        """
        self._supervisor_argv = supervisor_argv
        self._open: dict[int, Supervisor] = {}

    def start(self, argv: tuple[str, ...], env: tuple[tuple[str, str], ...]) -> Supervisor:
        """Start this instance's own supervisor, with `argv`/`env` as the one
        command it runs as its own child, and remember it by its pid for a later
        `await_done`/`close` to find.
        """
        supervisor = _start(self._supervisor_argv, argv, dict(env))
        self._open[supervisor.pid] = supervisor
        return supervisor

    def await_done(self, pid: int, deadline: float) -> int | None | SupervisorDoneUnknown:
        """Wait for the supervisor `start` identified as `pid` to report its one
        supervised command done, giving up once `deadline` passes.

        `SupervisorDoneUnknown` if `pid` names no supervisor this instance still has
        open -- `close` already removed it, or `start` was never called for it --
        the same "nothing further to recover" sentinel `_await_one_done` returns for
        every other way that can happen. A terminal outcome (an exit code, or
        `SupervisorDoneUnknown`) also closes and forgets this entry -- a timeout
        (`None`) does not, so a later `await_done` with a fresh `deadline` can still
        try again.
        """
        supervisor = self._open.get(pid)
        if supervisor is None:
            return SupervisorDoneUnknown()
        outcome = _await_one_done(supervisor, deadline)
        if outcome is None:
            return None
        supervisor.close()
        del self._open[pid]
        return outcome

    def close(self, pid: int) -> None:
        """Release whatever this instance is still holding open for the supervisor
        `start` identified as `pid`, once nothing will ask about it again.

        A no-op if `pid` names no supervisor this instance still has open --
        `await_done` already closed it on a terminal outcome, or nothing was ever
        started for it -- so a jail torn down without ever being awaited still gets
        its pipe closed here, from `destroy_jail`, without this call needing to know
        which case it is.
        """
        supervisor = self._open.pop(pid, None)
        if supervisor is not None:
            supervisor.close()
