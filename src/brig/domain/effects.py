"""The effects an operation or teardown generator yields (decision-0001 rule 10).

A driver performs each one and sends its result back with `send`. Values only: nothing here
does I/O (rule 2).
"""

from dataclasses import dataclass
from enum import StrEnum


class SignalKind(StrEnum):
    """A signal teardown may send a jail's process group, mildest first."""

    TERM = "TERM"
    KILL = "KILL"


class GroupState(StrEnum):
    """Whether a process group was found alive when verified."""

    GONE = "GONE"
    ALIVE = "ALIVE"


@dataclass(frozen=True)
class Process:
    """A started process's identity: enough to signal, verify or release it later."""

    pid: int
    pgid: int


@dataclass(frozen=True)
class StartSupervisedCommand:
    """Start the jail's supervisor, with `argv` in `env` as the one command it runs as its
    child (decision-0002). The driver sends back the supervisor's `Process`: the one process
    the host tracks. `env` is already scrubbed by `EnvPolicy`."""

    argv: tuple[str, ...]
    env: frozendict[str, str]


type Deadline = float
"""A `time.monotonic()` timestamp. The domain reads no clock (rule 2); the caller computes it."""


@dataclass(frozen=True)
class ExitCodeUnknown:
    """An exit code that can never be recovered: the process is no longer this program's child
    (`ECHILD`), or the supervisor's report is gone (its pipe closed or unreadable).

    Distinct from `None`, which means a deadline passed first and a later wait may still
    succeed."""


type ExitOutcome = int | None | ExitCodeUnknown
"""What `AwaitSupervisorDone` hands back: the exit code, `None` if `deadline` passed first,
or `ExitCodeUnknown`."""


@dataclass(frozen=True)
class AwaitSupervisorDone:
    """Wait, until `deadline`, for the supervisor named by `process` to report its command
    done. The driver sends back an `ExitOutcome`."""

    process: Process
    deadline: Deadline


@dataclass(frozen=True)
class SignalGroup:
    """Send `signal` to `process.pgid`. The driver sends back `None`."""

    process: Process
    signal: SignalKind


@dataclass(frozen=True)
class Verify:
    """Ask whether any process of `process.pgid` is still alive. The driver sends back a
    `GroupState`.

    With no `deadline`, one immediate check; with one, a poll until the group is gone or the
    deadline passes (the post-KILL rung: the kernel finishing a KILL is not instantaneous,
    TASK-0001.07). Either way the driver peeks the leader first and leaves a leader that has
    exited out of the check, without releasing it (decision-0003)."""

    process: Process
    deadline: Deadline | None = None


@dataclass(frozen=True)
class Release:
    """Release `process.pid` for reuse, once the ladder has checked it for the last time
    (decision-0003: `Verify` only peeks, so this is the one release). The driver sends back
    `None`."""

    process: Process


type Effect = StartSupervisedCommand | AwaitSupervisorDone | SignalGroup | Verify | Release
"""The closed set a generator may yield. Every match on one ends in `assert_never`, so a new
effect is a type error wherever it is not yet handled."""
