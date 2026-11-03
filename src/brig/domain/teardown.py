"""The verified kill ladder (decision-0001 rule 10): a generator of effects.

Verify before signalling, TERM before KILL, verify after every signal; a group found gone is
never signalled. The post-KILL verify carries a deadline and is a bounded poll, since the
kernel finishing a KILL is not instantaneous and a leader's exit says nothing about the rest of
its group (decision-0003, TASK-0001.07). Every verify only peeks the leader; the ladder's last
step, on every path, is `Release`, which frees its pid.
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
    """Verify `process`'s group is gone, escalating TERM then KILL while it is not, and return
    what the last verify found, after releasing `process`'s pid.

    `deadline` bounds the post-KILL verify's poll."""
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
