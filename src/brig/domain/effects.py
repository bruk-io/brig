"""Effect values an operation or teardown may yield.

Rule 10 (decision-0001): ``operations`` and ``teardown`` are generators that yield these
values, one effect at a time; a driver for the jail's type performs each one and sends
its result back into the generator with ``send``. This module only names the values --
no file here imports anything that does I/O (rule 2).

The walking skeleton (TASK-0001.03) needed exactly four effects: spawn the jail's one
process, reap its exit, signal its process group during teardown, and verify the group
is gone. `Reap`'s optional `deadline` (TASK-0001.06) lets a wait that is not already
bounded some other way give up instead of blocking forever. `SignalGroup` and `Verify`
stay exactly this shape for teardown's TERM/KILL escalation regardless of which effects
start and wait on the jail's process (decision-0002).

TASK-0001.15 adds `StartSupervisedCommand` and `AwaitSupervisorDone`, the supervised
path's counterparts to `Spawn` and `Reap`: once a supervisor is PID 1 inside the jail's
namespace, the host starts and waits on that one supervisor instead of spawning the
real command directly and tracking its process group from outside. `operations.py`'s
`create`/`start` yield these two for the normal path now (step 4); `Spawn`/`Reap` stay
named here for `teardown.py`'s own unchanged use of `Reap`, and for whatever jail type
or test still drives the direct-spawn shape by hand. Anything past that -- channels, the
full teardown ladder -- is a later slice's addition to this module, not a reason to
over-build it now.
"""

from dataclasses import dataclass
from enum import StrEnum


class SignalKind(StrEnum):
    """A signal teardown may send a jail's process group, oldest to harshest."""

    TERM = "TERM"
    KILL = "KILL"


class GroupState(StrEnum):
    """Whether a process group was found alive when verified."""

    GONE = "GONE"
    ALIVE = "ALIVE"


@dataclass(frozen=True)
class Process:
    """A spawned process's identity: enough to reap, signal or verify it later."""

    pid: int
    pgid: int


@dataclass(frozen=True)
class Spawn:
    """Start a jail's one process running `argv` in a new process group.

    `inheritable_fds` carries the jail type's own policy (`Plan.inheritable_fds`'s own
    docstring: TASK-0001.05 AC#1) for which fds that process may keep open across the
    spawn -- the complete allow-list, not an addition to any default. A driver performs
    this by creating the process, closing every open, inheritable fd not named here,
    and sends back its `Process`.
    """

    argv: tuple[str, ...]
    inheritable_fds: tuple[int, ...]


@dataclass(frozen=True)
class StartSupervisedCommand:
    """Start the jail's supervisor, with the one command it runs as its own child.

    The supervised path's counterpart to `Spawn` (decision-0002): instead of starting
    `argv` directly as this program's own child, with the host left tracking the
    resulting process *group* from outside the jail, a driver starts the supervisor --
    the file assembled from `infra/supervisor/wire.py` and `program.py`, dropped as
    PID 1 inside the jail's namespace -- and hands it `argv` and `env` to run as its
    one child. The driver sends back a `Process` identifying the supervisor itself:
    the single process this program now tracks, in place of the group `Spawn` left it
    tracking.

    `env` is a tuple of `(name, value)` pairs, not a mapping: domain types hold tuples
    (decision-0001 rule 8), and this interpreter has no immutable mapping type to use
    instead.

    `operations.create()` is this effect's real caller as of TASK-0001.15 step 4
    (decision-0001 rule 6's `under-exposed-access`/`over-exposed-module-symbol`);
    `presentation/drivers/bwrap.py` performs it, through `presentation/ports.py`'s
    `SupervisorPort`.

    Unresolved here: `Spawn`'s `inheritable_fds` names the jail type's complete fd
    allow-list for the process it starts (`plan.py`'s own docstring, TASK-0001.05
    AC#1). This effect carries no such field, so that policy is not yet represented on
    the supervised path -- which of the supervisor's own exec (`program.py`) or a
    later field here ends up enforcing it is still open, not settled by step 4 either.
    """

    argv: tuple[str, ...]
    env: tuple[tuple[str, str], ...]


type Deadline = float
"""A `time.monotonic()` timestamp: the latest moment a deadline-bound `Reap` may
still succeed. Domain does no I/O (rule 2), so nothing here reads the clock --
whoever drives the generator (presentation) reads it and hands in the timestamp.
"""


@dataclass(frozen=True)
class ExitCodeUnknown:
    """What a `Reap` or `_AwaitSupervisorDone` effect hands back in place of an exit
    code when the outcome waited for can never be recovered: for `Reap`, the process
    is no longer this program's child to wait for at all, something else already
    collected it; for `_AwaitSupervisorDone`, the supervisor's report of this process
    being done is gone for good (it already resolved some other wait, or the
    supervisor itself is gone).

    Distinct from `None`, which already means something else for a deadline-bound
    `Reap` (and, by the same reasoning, for `_AwaitSupervisorDone`): the clock reached
    `deadline` first with the outcome not in yet, so a later wait can still succeed --
    this outcome never resolves by waiting again. A driver recognizes infra's own
    version of this condition (`infra/processes.py`'s `ProcessUnknown`, an `ECHILD`
    from the OS, for `Reap`) and sends this value in its place, so nothing here ever
    needs to import infra's type to recognize it (rule 1; TASK-0001.06 review).
    """


@dataclass(frozen=True)
class Reap:
    """Wait for a process to exit and collect its exit code.

    A driver performs this by waiting on `process.pid` and sends back the exit
    code as an `int`, if it exits. Leave `deadline` unset where the wait is
    already bounded some other way (the teardown ladder's post-KILL reap,
    bounded by KILL itself); where nothing else bounds it, set `deadline` to a
    `time.monotonic()` timestamp, and the driver sends back `None` instead if
    the clock reaches it before the process exits -- the caller decides what a
    `None` means (an operation turns it into a brig error; this module only
    names the shape). Either way, the driver sends back `ExitCodeUnknown` instead if
    the process is no longer this program's child to wait for at all: nothing can
    recover its exit code now, regardless of whether `deadline` was set.
    """

    process: Process
    deadline: Deadline | None = None


type ExitOutcome = int | None | ExitCodeUnknown
"""What `AwaitSupervisorDone` hands back: the supervised command's exit code once the
supervisor reports it done, `None` if `deadline` arrived first with the supervisor not
yet done (a later `AwaitSupervisorDone` can still succeed), or `ExitCodeUnknown` if the
supervisor's report for this process can never be recovered now. The same three-way
split `Reap` already made for the direct-spawn path (`Reap`'s and `ExitCodeUnknown`'s
own docstrings), named here for reuse on this effect rather than respelled.
"""


@dataclass(frozen=True)
class AwaitSupervisorDone:
    """Wait for the supervisor to report its one supervised command done.

    The supervised path's counterpart to `Reap`: a driver performs this by waiting on
    the supervisor named by `process` -- through `infra/supervisor/link.py`'s wire
    protocol, not a direct OS wait on the real command itself -- and sends back an
    `ExitOutcome`. Unlike `Reap`, where `deadline` is optional because some waits are
    already bounded another way (the teardown ladder's post-KILL reap), nothing else
    bounds this wait, so `deadline` is required here: every `AwaitSupervisorDone`
    names a `time.monotonic()` timestamp past which the driver gives up and sends back
    `None` instead of blocking forever on a supervisor that never reports done.

    `operations.start()` is this effect's real caller as of TASK-0001.15 step 4, the
    same way `operations.create()` calls `StartSupervisedCommand`.
    """

    process: Process
    deadline: Deadline


@dataclass(frozen=True)
class SignalGroup:
    """Send a signal to a process group.

    A driver performs this by signalling `process.pgid` and sends back `None`.
    """

    process: Process
    signal: SignalKind


@dataclass(frozen=True)
class Verify:
    """Ask whether any process of a group is still alive.

    A driver performs this by checking `process.pgid` and sends back a
    `GroupState`.
    """

    process: Process


type Effect = Spawn | StartSupervisedCommand | Reap | AwaitSupervisorDone | SignalGroup | Verify
"""The closed set an operation or teardown generator may yield.

Every ``match`` on a yielded effect -- in a driver, or in a unit test driving the
generator by hand -- matches this union and ends with ``assert_never``, so a new
effect added here is a type error everywhere it is not yet handled.
"""
