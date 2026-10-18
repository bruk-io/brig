"""Effect values an operation or teardown may yield.

Rule 10 (decision-0001): ``operations`` and ``teardown`` are generators that yield these
values, one effect at a time; a driver for the jail's type performs each one and sends
its result back into the generator with ``send``. This module only names the values --
no file here imports anything that does I/O (rule 2).

The walking skeleton (TASK-0001.03) needed exactly four effects: spawn the jail's one
process, reap its exit, signal its process group during teardown, and verify the group
is gone. `Reap`'s optional `deadline` (TASK-0001.06) lets a wait that is not already
bounded some other way give up instead of blocking forever. Anything past that --
channels, the full teardown ladder -- is a later slice's addition to this module, not a
reason to over-build it now.
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


type Deadline = float
"""A `time.monotonic()` timestamp: the latest moment a deadline-bound `Reap` may
still succeed. Domain does no I/O (rule 2), so nothing here reads the clock --
whoever drives the generator (presentation) reads it and hands in the timestamp.
"""


@dataclass(frozen=True)
class ExitCodeUnknown:
    """What a `Reap` effect hands back in place of an exit code when the process
    waited for is no longer this program's child to wait for at all: something else
    already collected it, and its exit code cannot be recovered now.

    Distinct from `None`, which already means something else for a deadline-bound
    `Reap`: the clock reached `deadline` first with the process still running and
    left unreaped, so a later wait can still succeed -- this outcome never resolves
    by waiting again. A driver recognizes infra's own version of this condition
    (`infra/processes.py`'s `ProcessUnknown`, an `ECHILD` from the OS) and sends this
    value in its place, so nothing here ever needs to import infra's type to
    recognize it (rule 1; TASK-0001.06 review).
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


type Effect = Spawn | Reap | SignalGroup | Verify
"""The closed set an operation or teardown generator may yield.

Every ``match`` on a yielded effect -- in a driver, or in a unit test driving the
generator by hand -- matches this union and ends with ``assert_never``, so a new
effect added here is a type error everywhere it is not yet handled.
"""
