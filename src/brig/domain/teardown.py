"""The verified kill ladder (decision-0001 rule 10): a generator of effect values.

Verify before signalling, TERM before KILL, verify after every signal -- the order a
unit test drives this generator by hand to pin. The ladder escalates only while the
jail's process group is still found alive, so a process that already exited on its own
(`true`'s happy path in the walking skeleton) is never signalled at all: the first
`Verify` finds it gone and the generator returns without yielding anything else.

The ladder's last rung, after `SignalKind.KILL`, adds one more effect ahead of that
final `Verify`: a `Reap` of the leader, discarded. `SignalKind.KILL` cannot be caught
or ignored, so waiting for it to finish is bounded, not an open-ended block -- and
where the leader is still this program's child to wait for, blocking on it here is
what makes the last rung deterministic: a `Verify` run right after `KILL` with
nothing waited on first can still read the group as alive, because the kernel has not
yet finished the exit; collecting the leader here first means the `Verify` that
follows reliably sees it gone. The same reasoning does not hold after
`SignalKind.TERM`, which a process may ignore and never exit from, so that rung's
`Verify` stays non-blocking.

That determinism assumed a single-process jail, where the leader is the whole
group. Once the leader can already be gone by the time this `Reap` runs (an
`ExitCodeUnknown` leader already collected by an earlier rung's `Verify`, while the
rest of a multi-process group outlived it -- TASK-0001.06 review), this `Reap`
returns instantly instead of blocking, and provides no such guarantee for whatever
else is still in the group: the `Verify` right after can still -- correctly, not as
a bug in this module -- report the group alive for a few more moments while the
kernel finishes what `SignalKind.KILL` started. TASK-0001.07 tracks giving that case
a bounded grace window instead of one immediate check.

The general ladder (a grace period between TERM and KILL, a final failure if KILL
leaves the group alive) is a later slice's addition -- `domain/effects.py` names no
effect for a wait, and this module adds none on its own.
"""

from collections.abc import Generator
from typing import Any

from brig.domain.effects import (
    Effect,
    ExitCodeUnknown,
    GroupState,
    Process,
    Reap,
    SignalGroup,
    SignalKind,
    Verify,
)


def _verify(process: Process) -> Generator[Effect, Any, GroupState]:
    """Yield a Verify effect and narrow the driver's reply to a GroupState."""
    sent = yield Verify(process)
    assert isinstance(sent, GroupState)
    return sent


def _signal(process: Process, signal: SignalKind) -> Generator[Effect, Any]:
    """Yield a SignalGroup effect; a driver performs it and sends back None."""
    yield SignalGroup(process, signal)


def _reap_after_kill(process: Process) -> Generator[Effect, Any]:
    """Yield a Reap effect and discard whatever it collects; only its collection
    matters here.

    `sent` is ordinarily the leader's exit code, but can also be `ExitCodeUnknown`:
    the leader already collected by an earlier rung's `Verify` (whose non-blocking
    `reap_nowait` runs ahead of every check) while the rest of its group stayed alive
    -- the very group this rung's own `Verify`, right after this `Reap`, checks again.
    Both are fine to discard; only a value that is neither would mean the driver sent
    back something this ladder does not understand (TASK-0001.06 review).
    """
    sent = yield Reap(process)
    assert isinstance(sent, int) or isinstance(sent, ExitCodeUnknown)


def teardown(process: Process) -> Generator[Effect, Any, GroupState]:
    """Verify a jail's process group is gone, escalating TERM then KILL if not.

    Yields `Verify` first; if the group is already `GroupState.GONE`, returns that
    without signalling anything. Otherwise signals `SignalKind.TERM`, verifies again,
    and -- only if still alive -- signals `SignalKind.KILL`, reaps the leader (see the
    module docstring), and verifies once more. Returns whichever `GroupState` the last
    `Verify` found.
    """
    state = yield from _verify(process)
    if state is GroupState.GONE:
        return state

    yield from _signal(process, SignalKind.TERM)
    state = yield from _verify(process)
    if state is GroupState.GONE:
        return state

    yield from _signal(process, SignalKind.KILL)
    yield from _reap_after_kill(process)
    return (yield from _verify(process))
