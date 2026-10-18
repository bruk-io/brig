"""bwrap's driver (decision-0001 rule 10): performs an operation or teardown
generator's yielded effects.

The only module that knows both `brig.domain`'s effects and a `ProcessPort`/
`SupervisorPort`'s plain-data calls (rule 1): it translates one into the other, and
nothing else in presentation or domain does. A unit test for this slice drives the
domain generators by hand instead, exactly as this driver would, and needs no driver
at all.

TASK-0001.15 step 4: `StartSupervisedCommand`/`AwaitSupervisorDone` -- the normal
create/run path now (decision-0002) -- are performed through `SupervisorPort`, a new
parameter alongside `ProcessPort`. `Spawn`/`Reap`/`SignalGroup`/`Verify` stay
performed through `ProcessPort` exactly as before: `Spawn`/`Reap` for whatever still
drives the direct-spawn shape by hand, `SignalGroup`/`Verify` for teardown's
unchanged TERM/KILL escalation, which signals and probes the supervisor's own
pid/pgid the same way it always signalled and probed the real command's.

`.claude/rules/driver-exception-boundary.md`'s own discipline, re-run against this
module (TASK-0001.15/.17 adversarial review, then re-grepped over every arm rather
than only the one that review named -- that rule's whole point is that checking the
touched call site alone is what let this escape twice before). The arms that wrap a
port call in `try`/`except` are `Spawn`, `StartSupervisedCommand` and, new here,
`AwaitSupervisorDone`: each had an exception *measured* crossing it (`SpawnError`/
`OSError` for the first two; a raw `ValueError` out of `wire.decode_event` for the
third, past every caller that only ever named `wire.WireError`).

`Reap`, `SignalGroup` and `Verify` deliberately do not wrap theirs. Their ports are
documented to hand back a sentinel rather than raise -- `ProcessPort.reap`/
`reap_deadline` return `ProcessUnknown`, `reap_nowait` returns `None`,
`group_alive` returns a bool, and `signal_group` swallows an already-gone group
(`infra/processes.py`'s own docstring for it) -- so there is nothing here to
translate. That is a claim about those ports' contracts, not an exemption: should
any of them ever be measured raising, it is the same finding this module just fixed
for `AwaitSupervisorDone`, and the fix is another wrapped arm, not a wider `except`.
"""

import signal
from collections.abc import Generator
from typing import Any, assert_never, cast

from brig.domain.effects import (
    AwaitSupervisorDone,
    Effect,
    ExitCodeUnknown,
    GroupState,
    Process,
    Reap,
    SignalGroup,
    SignalKind,
    Spawn,
    StartSupervisedCommand,
    Verify,
)
from brig.infra.processes import SpawnError
from brig.infra.supervisor import wire
from brig.infra.supervisor.link import SupervisorSpawnError
from brig.presentation.errors import JailSpawnFailed
from brig.presentation.ports import (
    ProcessPort,
    ProcessUnknown,
    SupervisorDoneUnknown,
    SupervisorPort,
)

_SIGNALS: dict[SignalKind, signal.Signals] = {
    SignalKind.TERM: signal.SIGTERM,
    SignalKind.KILL: signal.SIGKILL,
}


def run[T](
    generator: Generator[Effect, Any, T],
    processes: ProcessPort,
    supervisors: SupervisorPort,
) -> T:
    """Drive `generator` to completion, performing each yielded effect through
    `processes` or `supervisors`.

    Raises:
        JailSpawnFailed: a `Spawn` or `StartSupervisedCommand` effect's process
            could not be started.
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
            case StartSupervisedCommand(argv=argv, env=env):
                try:
                    supervisor = supervisors.start(argv, env)
                except (SupervisorSpawnError, OSError) as exc:
                    raise JailSpawnFailed(argv) from exc
                sent = Process(pid=supervisor.pid, pgid=supervisor.pgid)
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
            case AwaitSupervisorDone(process=process, deadline=deadline):
                try:
                    supervisor_outcome = supervisors.await_done(process.pid, deadline)
                except OSError, wire.WireError:
                    # The driver exception boundary (decision-0001 rules 9/13;
                    # .claude/rules/driver-exception-boundary.md): a `SupervisorPort`
                    # is documented to never raise, but this call site is this
                    # module's one call into infra that was not actually guarded
                    # against it doing so anyway (TASK-0001.15/.17 adversarial
                    # review -- a raw `ValueError` measured escaping this exact
                    # path before `wire.decode_event` was fixed to never produce
                    # one). Folded into `ExitCodeUnknown`, the same "nothing further
                    # to recover" value `SupervisorDoneUnknown` already maps to just
                    # below: a wire this driver could not read is a report that can
                    # never be recovered either way, and `run_jail` already turns
                    # that into `JailExitUnknown`, a brig type an embedder can catch
                    # without ever naming `infra`'s own exceptions.
                    supervisor_outcome = SupervisorDoneUnknown()
                # Same translation, for the supervised path's own "gone for good"
                # sentinel (SupervisorPort's own docstring).
                sent = (
                    ExitCodeUnknown()
                    if isinstance(supervisor_outcome, SupervisorDoneUnknown)
                    else supervisor_outcome
                )
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
