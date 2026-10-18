"""Unit test for `operations.start`'s deadline-bound `AwaitSupervisorDone`
(TASK-0001.06 review; re-pointed at the supervised path by TASK-0001.15 step 4).

Drives `start` by hand, pinning that it narrows the driver's reply to the three
outcomes `AwaitSupervisorDone` can carry: an exit code, `None` once a deadline
passes, and `ExitCodeUnknown` once the supervisor's report for this process can
never be recovered -- distinct outcomes `presentation/api.py`'s `run_jail` turns into
different brig errors, and conflating the last two (review finding 3, on the earlier
direct-spawn `Reap`) would make a process whose exit code is gone for good look like
one still worth waiting for again.
"""

import pytest

from brig.domain.effects import AwaitSupervisorDone, ExitCodeUnknown, Process
from brig.domain.operations import start


def test_start_returns_exit_code_unknown_when_process_no_longer_a_child() -> None:
    """A driver's reply of `ExitCodeUnknown` passes straight through `start`."""
    process = Process(pid=55, pgid=55)
    gen = start(process, deadline=123.0)

    effect = next(gen)
    assert effect == AwaitSupervisorDone(process, 123.0)

    try:
        gen.send(ExitCodeUnknown())
    except StopIteration as stop:
        result = stop.value
    else:
        pytest.fail("start did not return after its AwaitSupervisorDone")

    assert result == ExitCodeUnknown()


def test_start_returns_none_when_the_deadline_passes() -> None:
    """A driver's reply of `None` (the deadline passed) also passes straight through,
    distinct from `ExitCodeUnknown`.
    """
    process = Process(pid=56, pgid=56)
    gen = start(process, deadline=99.0)

    next(gen)
    try:
        gen.send(None)
    except StopIteration as stop:
        result = stop.value
    else:
        pytest.fail("start did not return after its AwaitSupervisorDone")

    assert result is None


def test_start_returns_the_exit_code_when_the_process_exits() -> None:
    """The ordinary happy path: a driver's reply of an `int` passes straight through."""
    process = Process(pid=57, pgid=57)
    gen = start(process, deadline=42.0)

    next(gen)
    try:
        gen.send(7)
    except StopIteration as stop:
        result = stop.value
    else:
        pytest.fail("start did not return after its AwaitSupervisorDone")

    assert result == 7
