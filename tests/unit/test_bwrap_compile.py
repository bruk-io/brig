"""Unit tests for bwrap's compile and the create operation: `compile_run` names the command the
supervisor runs, `compile_supervisor_launch` wraps the supervisor in the compiled mounts and
bwrap's flags, and `create` yields the effect that starts it. The policy compile itself
(`compile_mounts`) is `test_fs_policy_compile.py`'s.
"""

import pytest
from tests.e2e.test_tiocsti_battery import _bwrap_argv_prefix

from brig.domain.channels import ChannelDirectory, Reservation, Reservations
from brig.domain.effects import Process, StartSupervisedCommand
from brig.domain.jail_types import bwrap
from brig.domain.operations import create
from brig.domain.policy.env import EnvPolicy
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY

_STATE_DIR = "/state/dir"
"""A stand-in for brig's resolved state directory: the compile treats it as a plain string."""

_SCRIPT = _STATE_DIR + "/brig-supervisor-x.py"
"""A stand-in for the supervisor script written into the state directory."""

_EMPTY = _STATE_DIR + "/empty"
"""A stand-in for brig's empty, read-only directory."""

_CHANNEL_DIR = _STATE_DIR + "/channels/abc"
"""A stand-in channel directory beneath the state directory, where the default places one."""

_CHANNELS = Reservations(
    directory=ChannelDirectory(host_path=_CHANNEL_DIR, jail_path=_CHANNEL_DIR),
    reservations=(
        Reservation(name="ctl", bound_path=_CHANNEL_DIR + "/ctl", endpoint=_CHANNEL_DIR + "/ctl"),
    ),
)


def _default_mounts(channels: Reservations | None = None) -> tuple[bwrap.Mount, ...]:
    return bwrap.compile_mounts(
        WHOLE_HOST_READ_ONLY,
        {},
        state_dir=_STATE_DIR,
        supervisor_script=_SCRIPT,
        empty_dir=_EMPTY,
        channels=channels,
    )


def test_bwrap_compile_run_names_the_real_command() -> None:
    """`compile_run` names the command the supervisor runs as its child, unwrapped."""
    plan = bwrap.compile_run(("true",))

    assert plan.argv == ("true",)
    assert plan.env == frozendict()


def test_bwrap_compile_supervisor_launch_wraps_the_given_path() -> None:
    """The default policy's one mount, the state directory's mask with this jail's script bound
    back and sealed (TASK-0019), the virtual filesystems, the namespace flags, then the
    supervisor."""
    argv = bwrap.compile_supervisor_launch(("python3", _SCRIPT), _default_mounts())

    assert argv == (
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        _STATE_DIR,
        "--ro-bind",
        _SCRIPT,
        _SCRIPT,
        "--remount-ro",
        _STATE_DIR,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/sys",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--as-pid-1",
        "--",
        "python3",
        _SCRIPT,
    )


def test_a_cwd_becomes_bwraps_chdir_just_before_the_namespace_flags() -> None:
    """TASK-0028: the supervisor starts in `cwd`, and its command inherits it."""
    argv = bwrap.compile_supervisor_launch(("python3", _SCRIPT), _default_mounts(), "/work")

    at = argv.index("--chdir")
    assert argv[at : at + 3] == ("--chdir", "/work", "--unshare-all")


def test_e2e_tiocsti_battery_bwrap_argv_prefix_matches_compile_supervisor_launch() -> None:
    """`tests/e2e/test_tiocsti_battery.py`'s `_bwrap_argv_prefix` is a hand copy of the default
    launch argv (rule 4 keeps that e2e test from importing the domain); this pins it to the real
    one, so a change to the compile not mirrored there fails here (TASK-0009)."""
    prefix = _bwrap_argv_prefix(_STATE_DIR, _SCRIPT)
    argv = bwrap.compile_supervisor_launch(("supervisor",), _default_mounts())

    assert argv[: len(prefix)] == prefix
    assert argv[len(prefix) :] == ("supervisor",)


def test_bwrap_compile_supervisor_launch_binds_the_channel_directory_inside_the_mask() -> None:
    """A declared channel adds one writable bind of its directory between the state
    directory's tmpfs and the seal that remounts it read-only (TASK-0001.25, TASK-0019)."""
    mounts = _default_mounts(_CHANNELS)

    assert mounts[-3:] == (
        bwrap.Mount(bwrap.MountKind.READ_ONLY, _SCRIPT, _SCRIPT),
        bwrap.Mount(bwrap.MountKind.WRITABLE, _CHANNEL_DIR, _CHANNEL_DIR),
        bwrap.Mount(bwrap.MountKind.REMOUNT_READ_ONLY, _STATE_DIR),
    )


def test_bwrap_compile_adds_no_channel_bind_when_none_is_declared() -> None:
    """Declaring no channel, an empty reservation set or none at all, adds nothing."""
    empty = Reservations(
        directory=ChannelDirectory(host_path=_CHANNEL_DIR, jail_path=_CHANNEL_DIR),
        reservations=(),
    )

    assert _default_mounts(empty) == _default_mounts()
    assert all(mount.target != _CHANNEL_DIR for mount in _default_mounts())


def test_bwrap_compile_shows_a_jail_only_its_own_script_and_channels_of_the_state_dir() -> None:
    """TASK-0019: of the state directory, which holds every jail's script and channels, the
    compile mounts only this jail's own two, after an empty tmpfs over it, even though the
    default policy's `/` covers it."""
    mounts = _default_mounts(_CHANNELS)
    under = [
        mount
        for mount in mounts
        if mount.kind in {bwrap.MountKind.READ_ONLY, bwrap.MountKind.WRITABLE}
        and mount.target.startswith(_STATE_DIR + "/")
    ]

    assert [mount.target for mount in under] == [_SCRIPT, _CHANNEL_DIR]
    assert mounts.index(bwrap.Mount(bwrap.MountKind.TMPFS, _STATE_DIR)) < mounts.index(under[0])


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
    assert effect == StartSupervisedCommand(("true",), frozendict())

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
    plan = bwrap.compile_run(("true",), env={"PATH": "/usr/bin", "SECRET": "shh"})
    policy = EnvPolicy(allowed=("PATH",))

    gen = create(plan, policy)

    effect = next(gen)
    assert effect == StartSupervisedCommand(("true",), frozendict({"PATH": "/usr/bin"}))

    try:
        gen.send(Process(pid=1, pgid=1))
    except StopIteration:
        pass
    else:
        pytest.fail("Generator did not return")
