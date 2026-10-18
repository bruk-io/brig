"""Unit test for bwrap's compile and the create operation (TASK-0001.03; re-pointed
at the supervised path by TASK-0001.15 step 4).

Tests the pure domain logic: `compile_run` names the real command (and its fd
policy) for the supervisor to run, `compile_supervisor_launch` wraps a given
supervisor path in bwrap's own flags, and the `create` generator yields a
`StartSupervisedCommand` with `compile_run`'s command/env, then returns the
Process the driver sends back.
"""

import pytest

from brig.domain.effects import Process, StartSupervisedCommand
from brig.domain.jail_types import bwrap
from brig.domain.operations import create
from brig.domain.policy.env import EnvPolicy
from brig.domain.policy.paths import Bind, FsPolicy


def test_bwrap_compile_run_names_the_real_command() -> None:
    """`compile_run` no longer wraps `command` in bwrap's own flags -- the jail's
    one process is the supervisor now, and `Plan.argv`/`Plan.env` are what it hands
    that supervisor to run as its own child.
    """
    plan = bwrap.compile_run(("true",))

    assert plan.argv == ("true",)
    assert plan.env == ()
    # TASK-0001.05 AC#1: bwrap's compile still states its own inheritable-fd policy,
    # even though the supervised path's StartSupervisedCommand has nowhere yet to
    # carry it (domain/jail_types/bwrap.py's own docstring on this field).
    assert plan.inheritable_fds == (0, 1, 2)


def test_bwrap_compile_supervisor_launch_wraps_the_given_path() -> None:
    """`compile_supervisor_launch` wraps whatever path it is given in bwrap's own
    namespace-isolation flags -- the job `compile_run` did for the real command
    directly before the supervisor existed to run it instead.
    """
    argv = bwrap.compile_supervisor_launch(("python3", "/path/to/program.py"))

    assert argv == (
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--as-pid-1",
        "--",
        "python3",
        "/path/to/program.py",
    )


def test_bwrap_compile_supervisor_launch_translates_a_custom_policys_binds() -> None:
    """TASK-0001.16 AC#2: a non-default `FsPolicy`'s binds become `--ro-bind`/
    `--bind` flags, one bind per flag triple, in the order `policy.binds` names
    them -- `--bind` for a writable `Bind`, `--ro-bind` otherwise -- ahead of the
    namespace-isolation flags, exactly where the single hardcoded placeholder bind
    used to sit.
    """
    policy = FsPolicy(
        binds=(
            Bind(host_path="/usr", jail_path="/usr"),
            Bind(host_path="/scratch", jail_path="/scratch", writable=True),
        )
    )

    argv = bwrap.compile_supervisor_launch(("python3", "/path/to/program.py"), policy)

    assert argv == (
        "bwrap",
        "--ro-bind",
        "/usr",
        "/usr",
        "--bind",
        "/scratch",
        "/scratch",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--as-pid-1",
        "--",
        "python3",
        "/path/to/program.py",
    )


def test_bwrap_create_true_generator() -> None:
    """Drive create's generator by hand for 'true'; verify effect order.

    This test verifies:
    - the create generator yields a StartSupervisedCommand with compile_run's
      command and environment
    - the generator returns the Process the driver sends back
    """
    plan = bwrap.compile_run(("true",))

    gen = create(plan)

    effect = next(gen)
    assert effect == StartSupervisedCommand(("true",), ())

    # Send back a mock Process (the supervisor's own pid/pgid, in a real journey)
    test_process = Process(pid=1234, pgid=1234)
    try:
        gen.send(test_process)
    except StopIteration as exc:
        # The generator returns the Process via StopIteration.value
        result = exc.value
    else:
        pytest.fail("Generator did not return")

    assert result == test_process


def test_bwrap_create_scrubs_plan_env_through_the_given_policy() -> None:
    """TASK-0001.17 AC#1: `create` filters `plan.env` down to exactly `policy`'s
    allow-list before the `StartSupervisedCommand` effect is built -- a name
    `policy` does not allow (`SECRET`) never reaches the effect, even though
    `compile_run`'s own candidate `env` carried it.
    """
    plan = bwrap.compile_run(("true",), env=(("PATH", "/usr/bin"), ("SECRET", "shh")))
    policy = EnvPolicy(allowed=("PATH",))

    gen = create(plan, policy)

    effect = next(gen)
    assert effect == StartSupervisedCommand(("true",), (("PATH", "/usr/bin"),))

    try:
        gen.send(Process(pid=1, pgid=1))
    except StopIteration:
        pass
    else:
        pytest.fail("Generator did not return")
