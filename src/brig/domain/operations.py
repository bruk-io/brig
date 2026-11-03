"""create, start and destroy: generators of effects (decision-0001 rule 10).

Each yields an `Effect` for a driver to perform (`presentation/driver.py`) and resumes with what
the driver sends back. The jail's one process is its supervisor (decision-0002).
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
    argv: tuple[str, ...], env: frozendict[str, str]
) -> Generator[Effect, Any, Process]:
    """Yield `StartSupervisedCommand` and narrow the reply to the supervisor's `Process`."""
    sent = yield StartSupervisedCommand(argv, env)
    assert isinstance(sent, Process)
    return sent


def _await_supervisor_done(
    process: Process, deadline: Deadline
) -> Generator[Effect, Any, ExitOutcome]:
    """Yield `AwaitSupervisorDone` and narrow the reply to an `ExitOutcome`."""
    sent = yield AwaitSupervisorDone(process, deadline)
    assert sent is None or isinstance(sent, int) or isinstance(sent, ExitCodeUnknown)
    return sent


def create(plan: Plan, policy: EnvPolicy = DENY_ALL) -> Generator[Effect, Any, Process]:
    """Start the jail's supervisor running `plan.argv`, in what of `plan.env` `policy` allows,
    and return the supervisor's `Process`.

    The environment is scrubbed here, before the effect is built, so nothing that performs it
    reads `os.environ`. `policy` defaults to `DENY_ALL`: no environment at all."""
    return (yield from _start_supervised(plan.argv, scrub_env(plan.env, policy)))


def start(process: Process, *, deadline: Deadline) -> Generator[Effect, Any, ExitOutcome]:
    """Wait for the supervisor to report its command done, until `deadline`, and return the
    `ExitOutcome`; the caller decides what `None` or `ExitCodeUnknown` becomes."""
    return (yield from _await_supervisor_done(process, deadline))


def destroy(process: Process, *, deadline: Deadline) -> Generator[Effect, Any, GroupState]:
    """Tear the jail down through the verified kill ladder (`domain/teardown.py`) and return
    what its last verify found; `deadline` bounds the post-KILL poll."""
    return (yield from _teardown.teardown(process, deadline=deadline))
