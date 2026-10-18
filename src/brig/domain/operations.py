"""create, start and destroy: generators of effect values (decision-0001 rule 10).

Each operation decides what should happen next and yields an `Effect` from
`domain/effects.py` for a driver to perform, resuming with whatever the driver sends
back. Nothing here does I/O (rule 2); the driver that performs these effects for bwrap
lives in `presentation/drivers/bwrap.py`.
"""

from collections.abc import Generator
from typing import Any

from brig.domain import teardown as _teardown
from brig.domain.effects import Deadline, Effect, ExitCodeUnknown, GroupState, Process, Reap, Spawn
from brig.domain.plan import Plan


def _spawn(
    argv: tuple[str, ...], inheritable_fds: tuple[int, ...]
) -> Generator[Effect, Any, Process]:
    """Yield a Spawn effect and narrow the driver's reply to a Process."""
    sent = yield Spawn(argv, inheritable_fds)
    assert isinstance(sent, Process)
    return sent


def _reap(
    process: Process, deadline: Deadline | None = None
) -> Generator[Effect, Any, int | None | ExitCodeUnknown]:
    """Yield a Reap effect and narrow the driver's reply to an exit code, None, or
    ExitCodeUnknown.

    `sent` is `None` only where `deadline` was given and the driver's wait reached it
    first; `ExitCodeUnknown` if the process is no longer this program's child to wait
    for at all, regardless of whether `deadline` was given (`effects.Reap`'s own
    docstring) -- the caller decides what either means.
    """
    sent = yield Reap(process, deadline)
    assert sent is None or isinstance(sent, int) or isinstance(sent, ExitCodeUnknown)
    return sent


def create(plan: Plan) -> Generator[Effect, Any, Process]:
    """Start a jail's one process running `plan.argv` in a new process group.

    A driver performs the yielded `Spawn` effect and sends back the `Process` it
    created. For a jail type whose one process *is* the jail (bwrap), creating the
    jail and starting its process are the same effect; a jail type with more to set up
    adds the effects for that here, ahead of this one.
    """
    return (yield from _spawn(plan.argv, plan.inheritable_fds))


def start(
    process: Process, *, deadline: Deadline | None = None
) -> Generator[Effect, Any, int | None | ExitCodeUnknown]:
    """Wait for the jail's process to exit and yield its exit code.

    A driver performs the yielded `Reap` effect and sends back the exit code. Leave
    `deadline` unset to wait with no bound of its own; set it to a `time.monotonic()`
    timestamp to give up and return `None` instead once the driver's wait reaches it,
    rather than blocking forever on a process that never exits on its own. Either way,
    returns `ExitCodeUnknown` instead if the process is no longer this program's child
    to wait for at all -- the caller decides what brig error either outcome becomes.
    """
    return (yield from _reap(process, deadline))


def destroy(process: Process) -> Generator[Effect, Any, GroupState]:
    """Tear the jail down, verified: no process of its group is left after.

    Delegates to `domain/teardown.py`'s ladder (verify, escalating signals, verify
    after each) and returns whatever `GroupState` its final verify found.
    """
    return (yield from _teardown.teardown(process))
