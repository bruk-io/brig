"""create, start and destroy: generators of effect values (decision-0001 rule 10).

Each operation decides what should happen next and yields an `Effect` from
`domain/effects.py` for a driver to perform, resuming with whatever the driver sends
back. Nothing here does I/O (rule 2); the driver that performs these effects for bwrap
lives in `presentation/drivers/bwrap.py`.

TASK-0001.15 step 4: `create`/`start` yield `StartSupervisedCommand`/
`AwaitSupervisorDone` now, in place of the direct `Spawn`/`Reap` shape the walking
skeleton used -- the jail's one process is its supervisor (decision-0002). `destroy`
works the same whichever kind of process `Process` names: teardown's `Verify`/
`SignalGroup`/`Release` ladder (decision-0003/TASK-0013) only ever reads `process`'s
`pid`/`pgid`, never anything specific to how it was started.
"""

from collections.abc import Generator
from typing import Any

from brig.domain import teardown as _teardown
from brig.domain.effects import (
    AwaitSupervisorDone,
    Deadline,
    Effect,
    ExitCodeUnknown,
    ExitOutcome,
    GroupState,
    Process,
    StartSupervisedCommand,
)
from brig.domain.plan import Plan
from brig.domain.policy.env import DENY_ALL, EnvPolicy, scrub_env


def _start_supervised(
    argv: tuple[str, ...], env: tuple[tuple[str, str], ...]
) -> Generator[Effect, Any, Process]:
    """Yield a StartSupervisedCommand effect and narrow the driver's reply to a
    Process: the supervisor's own identity, the one process the host now tracks in
    place of the group a direct `Spawn` left it tracking (decision-0002).
    """
    sent = yield StartSupervisedCommand(argv, env)
    assert isinstance(sent, Process)
    return sent


def _await_supervisor_done(
    process: Process, deadline: Deadline
) -> Generator[Effect, Any, ExitOutcome]:
    """Yield an AwaitSupervisorDone effect and narrow the driver's reply to an exit
    code, None, or ExitCodeUnknown -- the same three-way split `Reap` already made
    for the direct-spawn path (`effects.AwaitSupervisorDone`'s own docstring); the
    caller decides what either of the latter two means.
    """
    sent = yield AwaitSupervisorDone(process, deadline)
    assert sent is None or isinstance(sent, int) or isinstance(sent, ExitCodeUnknown)
    return sent


def create(plan: Plan, policy: EnvPolicy = DENY_ALL) -> Generator[Effect, Any, Process]:
    """Start the jail's supervisor as its one PID 1 process, with `plan.argv` as the
    real command it runs as its own child (decision-0002), in whatever of
    `plan.env` `policy`'s allow-list lets through.

    `plan.env` is `compile_run`'s own candidate environment (`domain/plan.py`'s own
    docstring) -- not yet scrubbed, since no jail type's compile reads `policy`
    (rule 2: compile does no I/O either, and a jail type is a slice, rule 3, with
    no reason to know this policy). `create` is TASK-0001.17's one caller of
    `scrub_env` (`domain/policy/env.py`): it filters `plan.env` down to exactly
    `policy.allowed` before the `StartSupervisedCommand` effect is even built, so
    the effect's own data is already scrubbed and nothing performing it -- a
    driver, or `infra/supervisor/link.py` underneath one -- ever reads `os.environ`
    itself to get there. `policy` defaults to `DENY_ALL`: a caller naming none of
    its own keeps the no-environment-at-all behaviour `Plan.env`'s own docstring
    already called a known, honestly-stated gap, rather than silently granting
    every name `plan.env` happens to carry.

    A driver performs the yielded `StartSupervisedCommand` effect and sends back the
    supervisor's own `Process` -- the single process this program now tracks, in
    place of the group a direct `Spawn` of the real command left it tracking.
    """
    scrubbed = scrub_env(dict(plan.env), policy)
    return (yield from _start_supervised(plan.argv, tuple(scrubbed.items())))


def start(process: Process, *, deadline: Deadline) -> Generator[Effect, Any, ExitOutcome]:
    """Wait for the supervisor to report the supervised command done, and yield its
    exit code.

    A driver performs the yielded `AwaitSupervisorDone` effect and sends back the
    exit code. `deadline`, a `time.monotonic()` timestamp, is required here --
    unlike the direct-spawn path's `Reap`, nothing else bounds this wait
    (`effects.AwaitSupervisorDone`'s own docstring) -- and the driver sends back
    `None` instead once its own wait reaches it, rather than blocking forever on a
    supervisor that never reports done. Either way, returns `ExitCodeUnknown`
    instead if the supervisor's report for this process can never be recovered now
    -- the caller decides what brig error either outcome becomes.
    """
    return (yield from _await_supervisor_done(process, deadline))


def destroy(process: Process, *, deadline: Deadline) -> Generator[Effect, Any, GroupState]:
    """Tear the jail down, verified: no process of its group is left after.

    Delegates to `domain/teardown.py`'s ladder (verify, escalating signals, verify
    after each) and returns whatever `GroupState` its final verify found. `deadline`,
    a `time.monotonic()` timestamp, bounds the post-KILL rung's grace-window poll
    (TASK-0001.07) -- domain does no I/O (rule 2), so the caller computes it.
    """
    return (yield from _teardown.teardown(process, deadline=deadline))
