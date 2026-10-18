"""bwrap's driver (decision-0001 rule 10): performs an operation or teardown
generator's yielded effects.

The only module that knows both `brig.domain`'s effects and a `ProcessPort`'s plain-data
calls (rule 1): it translates one into the other, and nothing else in presentation or
domain does. A unit test for this slice drives the domain generators by hand instead,
exactly as this driver would, and needs no driver at all.
"""

import signal
from collections.abc import Generator
from typing import Any, assert_never, cast

from brig.domain.effects import (
    Effect,
    ExitCodeUnknown,
    GroupState,
    Process,
    Reap,
    SignalGroup,
    SignalKind,
    Spawn,
    Verify,
)
from brig.infra.processes import SpawnError
from brig.presentation.errors import JailSpawnFailed
from brig.presentation.ports import ProcessPort, ProcessUnknown

_SIGNALS: dict[SignalKind, signal.Signals] = {
    SignalKind.TERM: signal.SIGTERM,
    SignalKind.KILL: signal.SIGKILL,
}


def run[T](generator: Generator[Effect, Any, T], processes: ProcessPort) -> T:
    """Drive `generator` to completion, performing each yielded effect through `processes`.

    Raises:
        JailSpawnFailed: a `Spawn` effect's process could not be started.
    """
    sent: Any = None
    effect = next(generator)
    while True:
        match effect:
            case Spawn(argv=argv, inheritable_fds=inheritable_fds):
                try:
                    spawned = processes.spawn(argv, inheritable_fds)
                except (SpawnError, OSError) as exc:
                    raise JailSpawnFailed(argv) from exc
                sent = Process(pid=spawned.pid, pgid=spawned.pgid)
            case Reap(process=process, deadline=deadline):
                outcome = (
                    processes.reap(process.pid)
                    if deadline is None
                    else processes.reap_deadline(process.pid, deadline)
                )
                # The port's own sentinel for "no longer this process's child to
                # wait for" (ECHILD) never crosses into domain -- translate it into
                # domain's own value here, the one place that knows both (rule 1).
                sent = ExitCodeUnknown() if isinstance(outcome, ProcessUnknown) else outcome
            case SignalGroup(process=process, signal=signal_kind):
                processes.signal_group(process.pgid, _SIGNALS[signal_kind])
                sent = None
            case Verify(process=process):
                # Collect the leader's exit status first, non-blocking, so a process
                # that already exited but was never reaped (a zombie) is freed before
                # the group check runs -- otherwise it would answer alive forever.
                # Only then is `group_alive` asked, over the whole group (`.pgid`),
                # never just the leader's `.pid`.
                processes.reap_nowait(process.pid)
                sent = GroupState.ALIVE if processes.group_alive(process.pgid) else GroupState.GONE
            case _ as unreachable:
                assert_never(unreachable)
        try:
            effect = generator.send(sent)
        except StopIteration as stop:
            return cast(T, stop.value)
