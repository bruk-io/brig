"""Unit test for the kill ladder's order (decision-0001 rule 10).

Rule 10: "Unit tests drive the generators by hand and pin the order: verify before
signalling, TERM before KILL, verify after." `tests/unit/test_bwrap_compile.py` covers
`compile_run` and `create`'s single `Spawn`; this module is `destroy`'s ladder, driven
by hand against a process that only gives up after both signals, so every rung --
including the `Reap` the ladder adds ahead of its last verify (`domain/teardown.py`'s
module docstring says why) -- is actually exercised, not just the happy path where the
first `Verify` already finds the group gone.
"""

import pytest

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
from brig.domain.teardown import teardown


def test_teardown_escalates_term_then_kill_verifying_at_every_step() -> None:
    """Drive `teardown` against a group that stays alive until KILL, by hand.

    Pins the whole order in one assertion: `Verify`, `SignalGroup(TERM)`, `Verify`,
    `SignalGroup(KILL)`, `Reap`, `Verify` -- verify before every signal, TERM before
    KILL, verify after each, and the deterministic reap ahead of the final verify.
    """
    process = Process(pid=4321, pgid=4321)
    gen = teardown(process)
    effects: list[Effect] = []

    effect = next(gen)
    effects.append(effect)
    effect = gen.send(GroupState.ALIVE)  # still alive -> escalate to TERM

    effects.append(effect)
    effect = gen.send(None)  # TERM sent -> verify again

    effects.append(effect)
    effect = gen.send(GroupState.ALIVE)  # still alive -> escalate to KILL

    effects.append(effect)
    effect = gen.send(None)  # KILL sent -> reap the leader

    effects.append(effect)
    effect = gen.send(99)  # reaped, exit code discarded -> verify once more

    effects.append(effect)
    try:
        gen.send(GroupState.GONE)  # now gone -> teardown returns
    except StopIteration as stop:
        result = stop.value
    else:
        pytest.fail("teardown did not return after its last verify")

    assert effects == [
        Verify(process),
        SignalGroup(process, SignalKind.TERM),
        Verify(process),
        SignalGroup(process, SignalKind.KILL),
        Reap(process),
        Verify(process),
    ]
    assert result is GroupState.GONE


def test_teardown_tolerates_leader_already_reaped_after_kill() -> None:
    """The post-KILL `Reap` can collect `ExitCodeUnknown` instead of an exit code --
    the leader already reaped by an earlier rung's `Verify` while the rest of its
    group stayed alive -- and `teardown` still completes rather than raising
    `AssertionError` (TASK-0001.06 review: a leader that exits before the rest of its
    group, reaped by `Verify`'s own non-blocking `reap_nowait`, left nothing for this
    `Reap` to collect by the time the ladder reaches it).
    """
    process = Process(pid=5555, pgid=5555)
    gen = teardown(process)
    effects: list[Effect] = []

    effect = next(gen)
    effects.append(effect)
    effect = gen.send(GroupState.ALIVE)  # still alive -> escalate to TERM

    effects.append(effect)
    effect = gen.send(None)  # TERM sent -> verify again

    effects.append(effect)
    effect = gen.send(GroupState.ALIVE)  # still alive -> escalate to KILL

    effects.append(effect)
    effect = gen.send(None)  # KILL sent -> reap the leader

    effects.append(effect)
    effect = gen.send(ExitCodeUnknown())  # leader already reaped elsewhere -> verify once more

    effects.append(effect)
    try:
        gen.send(GroupState.GONE)  # now gone -> teardown returns
    except StopIteration as stop:
        result = stop.value
    else:
        pytest.fail("teardown did not return after its last verify")

    assert effects == [
        Verify(process),
        SignalGroup(process, SignalKind.TERM),
        Verify(process),
        SignalGroup(process, SignalKind.KILL),
        Reap(process),
        Verify(process),
    ]
    assert result is GroupState.GONE


def test_teardown_returns_gone_without_signalling_when_already_gone() -> None:
    """A group the first `Verify` already finds gone is never signalled at all."""
    process = Process(pid=1111, pgid=1111)
    gen = teardown(process)

    effect = next(gen)
    assert effect == Verify(process)

    try:
        gen.send(GroupState.GONE)
    except StopIteration as stop:
        result = stop.value
    else:
        pytest.fail("teardown did not return after its first verify")

    assert result is GroupState.GONE
