"""Unit test for bwrap's compile and the create operation (TASK-0001.03).

Tests the pure domain logic: compile generates the correct argv, and the create
generator yields the Spawn effect with that argv, then returns the Process.
"""

import pytest

from brig.domain.effects import Process, Spawn
from brig.domain.jail_types import bwrap
from brig.domain.operations import create


def test_bwrap_create_true_generator() -> None:
    """Drive create's generator by hand for 'true'; verify argv and effect order.

    The walking skeleton compiles a request to run 'true' in a bwrap jail,
    spawns it, and returns the Process. This test verifies:
    - compile_run produces the expected argv (bwrap flags + 'true')
    - the create generator yields a Spawn with that argv
    - the generator returns the Process the driver sends back
    """
    # Compile: bwrap should produce argv with a filesystem bind, the unshare and
    # die-with-parent flags, and 'true'
    plan = bwrap.compile_run(("true",))
    expected_argv = (
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--",
        "true",
    )
    assert plan.argv == expected_argv
    # TASK-0001.05 AC#1: bwrap's compile states its own inheritable-fd policy --
    # just the jailed command's own standard streams, nothing an embedder had open.
    assert plan.inheritable_fds == (0, 1, 2)

    # Create: drive the generator by hand
    gen = create(plan)

    # First yield should be Spawn with the compiled argv
    effect = next(gen)
    assert isinstance(effect, Spawn)
    assert effect.argv == expected_argv
    # The plan's inheritable-fd policy rides along on the Spawn effect, for a
    # driver to enforce when it performs it (TASK-0001.05 AC#1).
    assert effect.inheritable_fds == (0, 1, 2)

    # Send back a mock Process (pid and pgid for a hypothetical spawned process)
    test_process = Process(pid=1234, pgid=1234)
    try:
        gen.send(test_process)
    except StopIteration as exc:
        # The generator returns the Process via StopIteration.value
        result = exc.value
    else:
        pytest.fail("Generator did not return")

    assert result == test_process
