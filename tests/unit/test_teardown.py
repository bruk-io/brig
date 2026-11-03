"""Unit test for the kill ladder's order (decision-0001 rule 10): verify before signalling, TERM
before KILL, verify after, and `Release` before every return, driven by hand against a group
that gives up only after both signals."""

import pytest

from brig.domain.effects import (
    Effect,
    GroupState,
    Process,
    Release,
    SignalGroup,
    SignalKind,
    Verify,
)
from brig.domain.teardown import teardown

_DEADLINE = 123.0
"""An arbitrary `time.monotonic()` timestamp: `teardown` never reads the clock
itself (domain does no I/O, rule 2), so any fixed value pins the post-KILL rung's
`Verify.deadline` deterministically without this module needing a real one.
"""


def test_teardown_escalates_term_then_kill_verifying_at_every_step() -> None:
    """Drive `teardown` against a group that stays alive until KILL, by hand.

    Pins the whole order in one assertion: `Verify`, `SignalGroup(TERM)`, `Verify`,
    `SignalGroup(KILL)`, `Verify(deadline=...)`, `Release` -- verify before every
    signal, TERM before KILL, verify after each, the post-KILL rung's bounded grace
    window (TASK-0001.07), and the terminal release once the ladder is done.
    """
    process = Process(pid=4321, pgid=4321)
    gen = teardown(process, deadline=_DEADLINE)
    effects: list[Effect] = []

    effect = next(gen)
    effects.append(effect)
    effect = gen.send(GroupState.ALIVE)  # still alive -> escalate to TERM

    effects.append(effect)
    effect = gen.send(None)  # TERM sent -> verify again

    effects.append(effect)
    effect = gen.send(GroupState.ALIVE)  # still alive -> escalate to KILL

    effects.append(effect)
    effect = gen.send(None)  # KILL sent -> verify once more, bounded by deadline

    effects.append(effect)
    effect = gen.send(GroupState.GONE)  # now gone -> release the pid

    effects.append(effect)
    try:
        gen.send(None)  # released -> teardown returns
    except StopIteration as stop:
        result = stop.value
    else:
        pytest.fail("teardown did not return after releasing its pid")

    assert effects == [
        Verify(process),
        SignalGroup(process, SignalKind.TERM),
        Verify(process),
        SignalGroup(process, SignalKind.KILL),
        Verify(process, deadline=_DEADLINE),
        Release(process),
    ]
    assert result is GroupState.GONE


def test_teardown_returns_gone_without_signalling_when_already_gone() -> None:
    """A group the first `Verify` already finds gone is never signalled at all, but
    its pid is still released before `teardown` returns (decision-0003/TASK-0013:
    `Verify` only ever peeks, so even the walking skeleton's already-exited `true`
    leaves a zombie behind for this ladder's own terminal step to release).
    """
    process = Process(pid=1111, pgid=1111)
    gen = teardown(process, deadline=_DEADLINE)

    effect = next(gen)
    assert effect == Verify(process)

    effect = gen.send(GroupState.GONE)
    assert effect == Release(process)

    try:
        gen.send(None)
    except StopIteration as stop:
        result = stop.value
    else:
        pytest.fail("teardown did not return after releasing its pid")

    assert result is GroupState.GONE
