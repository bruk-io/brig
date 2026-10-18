"""The verified kill ladder (decision-0001 rule 10): a generator of effect values.

Verify before signalling, TERM before KILL, verify after every signal -- the order a
unit test drives this generator by hand to pin. The ladder escalates only while the
jail's process group is still found alive, so a process that already exited on its own
(`true`'s happy path in the walking skeleton) is never signalled at all: the first
`Verify` finds it gone and the generator returns without yielding anything else.

The ladder's last rung, after `SignalKind.KILL`, used to add one more effect ahead of
its final `Verify`: a blocking `Reap` of the leader, discarded, relied on as a
synchronization barrier -- waiting for the leader to exit was supposed to guarantee
the kernel had finished processing `SignalKind.KILL` by the time the `Verify` right
after it ran. That reasoning assumed a single-process jail, where the leader is the
whole group; once the leader can already be gone by the time that `Reap` would run (an
`ExitCodeUnknown` leader already collected by an earlier rung's `Verify`, while the
rest of a multi-process group outlived it -- TASK-0001.06 review), the `Reap` returned
instantly and gave no such guarantee for whatever else was still in the group, so the
`Verify` right after could still -- correctly, not as a bug -- report the group alive
for a few more moments while the kernel finished what `KILL` started (TASK-0001.07).

decision-0003/TASK-0013 replaces that rung's `Reap`-then-`Verify` pair with a single
`Verify(process, deadline=...)`: a driver performs this one effect as a bounded poll
(`infra/processes.py`'s `group_alive_deadline`) rather than one immediate check, which
subsumes the old barrier for both the single- and multi-process cases -- there is no
longer a separate `Reap` step to rely on, or to tolerate an `ExitCodeUnknown` from.

Every rung's `Verify` -- immediate or deadline-bound -- peeks the group's leader
before checking the group (a driver's own job, `infra/processes.py`'s `peek`), rather
than releasing it: decision-0003's fix for the raw pid-reuse hazard a plain,
unconditional reap left open between one check and the next. Once this ladder returns
-- `GroupState.GONE` or not, its last word on `process` either way -- nothing will
ever check that pid again, so this module's last act before returning, on every exit
path, is `Release(process)`: the terminal step that actually frees the pid the
ladder's own `Verify` calls have only ever peeked.

The general ladder (a grace period between TERM and KILL, a final failure if KILL
leaves the group alive) is a later slice's addition -- `domain/effects.py` names no
effect for a wait between TERM and KILL, and this module adds none on its own.
"""

from collections.abc import Generator
from typing import Any

from brig.domain.effects import (
    Deadline,
    Effect,
    GroupState,
    Process,
    Release,
    SignalGroup,
    SignalKind,
    Verify,
)


def _verify(
    process: Process, *, deadline: Deadline | None = None
) -> Generator[Effect, Any, GroupState]:
    """Yield a Verify effect and narrow the driver's reply to a GroupState."""
    sent = yield Verify(process, deadline)
    assert isinstance(sent, GroupState)
    return sent


def _signal(process: Process, signal: SignalKind) -> Generator[Effect, Any]:
    """Yield a SignalGroup effect; a driver performs it and sends back None."""
    yield SignalGroup(process, signal)


def _release(process: Process) -> Generator[Effect, Any]:
    """Yield a Release effect; a driver performs it and sends back None."""
    yield Release(process)


def teardown(process: Process, *, deadline: Deadline) -> Generator[Effect, Any, GroupState]:
    """Verify a jail's process group is gone, escalating TERM then KILL if not.

    Yields `Verify` first; if the group is already `GroupState.GONE`, releases
    `process`'s pid and returns that state without signalling anything. Otherwise
    signals `SignalKind.TERM`, verifies again (releasing and returning the same way
    if now gone), and -- only if still alive -- signals `SignalKind.KILL` and
    verifies once more with `deadline` (the post-KILL grace window, TASK-0001.07),
    bounding how long that last `Verify` polls before giving up. Releases `process`'s
    pid and returns whichever `GroupState` that last `Verify` found, either way: the
    ladder is done checking this pid for good by the time it returns, win or lose
    (module docstring).

    `deadline`, a `time.monotonic()` timestamp, is required because the post-KILL
    rung always needs one -- domain does no I/O (rule 2), so this module cannot
    compute it itself; the caller does.
    """
    state = yield from _verify(process)
    if state is GroupState.GONE:
        yield from _release(process)
        return state

    yield from _signal(process, SignalKind.TERM)
    state = yield from _verify(process)
    if state is GroupState.GONE:
        yield from _release(process)
        return state

    yield from _signal(process, SignalKind.KILL)
    state = yield from _verify(process, deadline=deadline)
    yield from _release(process)
    return state
