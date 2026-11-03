"""The effect interpreter every jail type shares (decision-0001 rule 10, decision-0007 item 5):
performs each effect a domain generator yields through a `ProcessPort` or `SupervisorPort`.

The driver exception boundary (`.claude/rules/driver-exception-boundary.md`): the arms that
call `SupervisorPort.start` and `await_done` catch what was measured crossing them (`OSError`
and `SupervisorSpawnError` from a start; `OSError` and `wire.WireError` from a read, TASK-0001.15).
The other ports return a value and never raise; one measured raising gets a wrapped arm too.
"""

import signal
from collections.abc import Generator
from typing import Any, assert_never, cast

from brig.domain.effects import (
    AwaitSupervisorDone,
    Effect,
    ExitCodeUnknown,
    ExitOutcome,
    GroupState,
    Process,
    Release,
    SignalGroup,
    SignalKind,
    StartSupervisedCommand,
    Verify,
)
from brig.infra.supervisor import wire
from brig.infra.supervisor.link import SupervisorSpawnError
from brig.presentation.errors import JailSpawnFailed
from brig.presentation.ports import ProcessPort, SupervisorPort

_SIGNALS: frozendict[SignalKind, signal.Signals] = frozendict(
    {
        SignalKind.TERM: signal.SIGTERM,
        SignalKind.KILL: signal.SIGKILL,
    }
)


def run[T](
    generator: Generator[Effect, Any, T],
    processes: ProcessPort,
    supervisors: SupervisorPort,
) -> T:
    """Drive `generator` to completion, performing each yielded effect through `processes` or
    `supervisors`, and return its result.

    Raises:
        JailSpawnFailed: a `StartSupervisedCommand`'s supervisor could not be started.
    """
    sent: Any = None
    effect = next(generator)
    while True:
        match effect:
            case StartSupervisedCommand(argv=argv, env=env):
                try:
                    supervisor = supervisors.start(argv, env)
                except (SupervisorSpawnError, OSError) as exc:
                    raise JailSpawnFailed(argv) from exc
                sent = Process(pid=supervisor.pid, pgid=supervisor.pgid)
            case AwaitSupervisorDone(process=process, deadline=deadline):
                outcome: ExitOutcome
                try:
                    outcome = supervisors.await_done(process.pid, deadline)
                except OSError, wire.WireError:
                    # A wire that cannot be read is a report that can never be recovered.
                    outcome = ExitCodeUnknown()
                sent = outcome
            case SignalGroup(process=process, signal=signal_kind):
                processes.signal_group(process.pgid, _SIGNALS[signal_kind])
                sent = None
            case Verify(process=process, deadline=deadline):
                if deadline is None:
                    # A leader that exited is held, not released: left out of the check, and
                    # peeked afresh on every Verify since peeking never consumes it.
                    exited = processes.peek(process.pid)
                    held = frozenset({process.pid}) if isinstance(exited, int) else frozenset()
                    alive = processes.group_alive(process.pgid, held)
                else:
                    alive = processes.group_alive_deadline(process.pid, process.pgid, deadline)
                sent = GroupState.ALIVE if alive else GroupState.GONE
            case Release(process=process):
                processes.release(process.pid)
                sent = None
            case _ as unreachable:
                assert_never(unreachable)
        try:
            effect = generator.send(sent)
        except StopIteration as stop:
            return cast(T, stop.value)
