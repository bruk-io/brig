"""Unit test for bwrap's compile and the create operation (TASK-0001.03; re-pointed
at the supervised path by TASK-0001.15 step 4).

Tests the pure domain logic: `compile_run` names the real command (and its fd
policy) for the supervisor to run, `compile_supervisor_launch` wraps a given
supervisor path in bwrap's own flags, and the `create` generator yields a
`StartSupervisedCommand` with `compile_run`'s command/env, then returns the
Process the driver sends back.
"""

import pytest
from tests.e2e.test_tiocsti_battery import _bwrap_argv_prefix

from brig.domain.channels import ChannelDirectory, Reservation, Reservations
from brig.domain.effects import Process, StartSupervisedCommand
from brig.domain.jail_types import bwrap
from brig.domain.operations import create
from brig.domain.policy.env import EnvPolicy
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, Bind, FsPolicy

_STATE_DIR_PLACEHOLDER = "/state/dir/placeholder"
"""A plain string stand-in for TASK-0006's resolved state directory: domain's own
`compile_supervisor_launch` treats `state_dir` as an opaque string (rule 2 -- it
does no I/O to resolve or create one itself), so any string proves the same thing
a real resolved path would about where the unconditional bind's triple lands.
"""


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

    TASK-0006: also asserts the unconditional `state_dir` bind lands right after
    the (default) policy's own one bind and before the namespace-isolation
    flags -- the exact position that lets it win over an overlapping policy bind
    (bwrap applies binds in argv order) without being part of the policy itself.
    """
    argv = bwrap.compile_supervisor_launch(
        ("python3", "/path/to/program.py"), state_dir=_STATE_DIR_PLACEHOLDER
    )

    assert argv == (
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--ro-bind",
        _STATE_DIR_PLACEHOLDER,
        _STATE_DIR_PLACEHOLDER,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/sys",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--as-pid-1",
        "--",
        "python3",
        "/path/to/program.py",
    )


def test_e2e_tiocsti_battery_bwrap_argv_prefix_matches_compile_supervisor_launch() -> None:
    """TASK-0009: `tests/e2e/test_tiocsti_battery.py`'s `_bwrap_argv_prefix` is a
    hand-maintained copy of `compile_supervisor_launch`'s real output, kept as a
    literal there because decision-0001 rule 4 bars that e2e test from importing a
    `domain` module directly. This test lives in the one layer allowed to know
    both: it imports the e2e function (not a `brig` import, so rule 4's own
    `tests/unit` check -- which only restricts `brig` imports -- does not apply to
    it) and asserts it against `compile_supervisor_launch`'s actual compiled output
    for the same (default `WHOLE_HOST_READ_ONLY`) policy, so a future change to the
    real argv that isn't mirrored in the e2e copy fails here, loudly, instead of
    leaving that copy silently stale (TASK-0009's own history: it already drifted
    once, missing `--as-pid-1` after TASK-0001.15 step 4 added it).

    Everything up to the supervisor's own path is asserted equal, not merely a
    subsequence: `_bwrap_argv_prefix` claims to be exactly the bind and
    namespace-isolation flags ahead of wherever the supervisor path lands, so this
    pins that whole prefix, not just its presence somewhere in the output.

    TASK-0006: the e2e module's prefix has its own unconditional state-dir bind to
    mirror too, so this feeds `_STATE_DIR_PLACEHOLDER` -- the same plain string
    `test_bwrap_compile_supervisor_launch_wraps_the_given_path` above already uses
    -- to *both* sides (`_bwrap_argv_prefix` and `compile_supervisor_launch`
    directly): the triple's own position in the argv is what this test grades, not
    the real path's own value, and `compile_supervisor_launch` treats `state_dir`
    as an opaque string regardless (rule 2 -- it does no I/O to resolve one).

    Adversarial review of TASK-0009's first version (this file importing
    `tests.e2e.test_tiocsti_battery._resolved_state_dir` and calling it directly)
    found that call performing real filesystem I/O -- recreating `~/.brig` on
    every `just test-unit` run -- and reading `os.environ`, inside a layer whose
    own rule (and the owner's own unit-tests rule) says neither happens. Fixed by
    parameterising `_bwrap_argv_prefix` (`state_dir: str`) so it is a pure function
    of whatever string it is given, same as `compile_supervisor_launch` itself;
    this test now gives both sides the identical placeholder and performs no real
    I/O of its own. Confirmed the assertion still discriminates with that one
    placeholder fed to both sides: it fails on a flag reordered, a flag missing, or
    a bind triple missing, the same as it would with the real resolved path.

    What this parameterisation does not fix: importing
    `tests.e2e.test_tiocsti_battery` at all, even for this one now-pure function,
    still pulls `brig`, `brig.domain.*`, `brig.infra.*` and `brig.presentation.*`
    into this unit test's import graph through that module's own `from brig import
    ...` -- a tests-to-tests hop `brig-test-layers`'s own `_unit_test_violations`
    check does not see, because it inspects only direct `brig.*` imports. DRAFT-0013
    is the open board question for exactly this gap; this test stands on it,
    unresolved, the same as TASK-0009's original version did.
    """
    prefix = _bwrap_argv_prefix(_STATE_DIR_PLACEHOLDER)
    argv = bwrap.compile_supervisor_launch(
        ("supervisor-placeholder",), state_dir=_STATE_DIR_PLACEHOLDER, policy=WHOLE_HOST_READ_ONLY
    )

    assert argv[: len(prefix)] == prefix
    assert argv[len(prefix) :] == ("supervisor-placeholder",)


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

    argv = bwrap.compile_supervisor_launch(
        ("python3", "/path/to/program.py"), state_dir=_STATE_DIR_PLACEHOLDER, policy=policy
    )

    assert argv == (
        "bwrap",
        "--ro-bind",
        "/usr",
        "/usr",
        "--bind",
        "/scratch",
        "/scratch",
        "--ro-bind",
        _STATE_DIR_PLACEHOLDER,
        _STATE_DIR_PLACEHOLDER,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/sys",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--as-pid-1",
        "--",
        "python3",
        "/path/to/program.py",
    )


_CHANNEL_DIR = _STATE_DIR_PLACEHOLDER + "/channels/abc"
"""A plain-string channel directory beneath the state-dir placeholder, where
`presentation/api.py`'s default places one."""


def test_bwrap_compile_supervisor_launch_binds_the_channel_directory_for_declared_channels() -> (
    None
):
    """TASK-0001.25 AC#2: a declared channel adds exactly one writable `--bind` of the
    per-jail channel directory, host path to jail path, right after the read-only
    `state_dir` bind (the channel directory lives beneath it, and bwrap's later bind
    wins) and before the virtual-fs flags.
    """
    channels = Reservations(
        directory=ChannelDirectory(host_path=_CHANNEL_DIR, jail_path="/jail/side"),
        reservations=(
            Reservation(name="ctl", bound_path=_CHANNEL_DIR + "/ctl", endpoint="/jail/side/ctl"),
        ),
    )

    argv = bwrap.compile_supervisor_launch(
        ("python3", "/path/to/program.py"), state_dir=_STATE_DIR_PLACEHOLDER, channels=channels
    )

    assert argv == (
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--ro-bind",
        _STATE_DIR_PLACEHOLDER,
        _STATE_DIR_PLACEHOLDER,
        "--bind",
        _CHANNEL_DIR,
        "/jail/side",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/sys",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--as-pid-1",
        "--",
        "python3",
        "/path/to/program.py",
    )


def test_bwrap_compile_supervisor_launch_adds_no_bind_when_no_channel_is_declared() -> None:
    """TASK-0001.25 AC#2: declaring no channel -- an empty reservation set, or none at
    all -- leaves the argv exactly what it is without the parameter: no `--bind`, and
    the channel directory named nowhere.
    """
    without = bwrap.compile_supervisor_launch(
        ("python3", "/path/to/program.py"), state_dir=_STATE_DIR_PLACEHOLDER
    )
    empty = bwrap.compile_supervisor_launch(
        ("python3", "/path/to/program.py"),
        state_dir=_STATE_DIR_PLACEHOLDER,
        channels=Reservations(
            directory=ChannelDirectory(host_path=_CHANNEL_DIR, jail_path=_CHANNEL_DIR),
            reservations=(),
        ),
    )

    assert empty == without
    assert "--bind" not in empty
    assert _CHANNEL_DIR not in empty


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


def test_covering_ancestor_bind_is_none_with_no_binds_at_all() -> None:
    """TASK-0001.22: an empty policy names no ancestor of `state_dir` at all --
    bwrap's own new root starts as a writable tmpfs, so this is one of the safe
    cases `presentation/api.py`'s `_check_state_dir_reachable` never refuses.
    """
    policy = FsPolicy(binds=())

    assert bwrap.covering_ancestor_bind(policy, "/custom/brig-state") is None


def test_covering_ancestor_bind_is_none_for_a_bind_at_the_exact_same_path() -> None:
    """A bind at exactly `state_dir`'s own jail path is not an *ancestor* bind --
    that is `compile_supervisor_launch`'s own unconditional bind's job, and the
    "does not shadow it" guarantee `tests/e2e/test_fs_policy_battery.py` already
    covers for the exact-path case, not this function's.
    """
    policy = FsPolicy(binds=(Bind(host_path="/elsewhere", jail_path="/custom/brig-state"),))

    assert bwrap.covering_ancestor_bind(policy, "/custom/brig-state") is None


def test_covering_ancestor_bind_is_none_for_a_sibling_or_a_descendant() -> None:
    """A bind at a path that is not a prefix of `state_dir` at all (a sibling), or
    one nested *inside* `state_dir` (a descendant), governs neither `state_dir`
    itself nor any of its ancestors, so neither is returned.
    """
    policy = FsPolicy(
        binds=(
            Bind(host_path="/elsewhere", jail_path="/custom/other"),
            Bind(host_path="/elsewhere", jail_path="/custom/brig-state/nested"),
        )
    )

    assert bwrap.covering_ancestor_bind(policy, "/custom/brig-state") is None


def test_covering_ancestor_bind_finds_a_single_ancestor() -> None:
    """The one bind whose own `jail_path` is a strict ancestor of `state_dir` is
    returned, whether or not it is writable -- `presentation/api.py`'s own
    `_check_state_dir_reachable` is what decides whether a *read-only* one like
    this actually blocks `state_dir` (the one host filesystem check rule 2 keeps
    out of this pure function).
    """
    ancestor = Bind(host_path="/host-custom", jail_path="/custom")
    policy = FsPolicy(binds=(ancestor,))

    assert bwrap.covering_ancestor_bind(policy, "/custom/brig-state") == ancestor


def test_covering_ancestor_bind_prefers_the_last_matching_ancestor_in_argv_order() -> None:
    """Two binds both ancestors of `state_dir`, nested one inside the other: bwrap
    mounts in argv order and a later mount at a path replaces the whole view
    beneath it, so the *last* one in `policy.binds` -- not the first, and not the
    most deeply nested one, if that is not also the last -- is the one actually
    governing `state_dir`'s own parent once every one of `policy`'s own binds has
    applied.
    """
    outer = Bind(host_path="/host-outer", jail_path="/custom")
    inner = Bind(host_path="/host-inner", jail_path="/custom/level1", writable=True)
    policy = FsPolicy(binds=(outer, inner))

    assert bwrap.covering_ancestor_bind(policy, "/custom/level1/level2") == inner
    # Order matters: with the same two binds reversed, the outer one is last
    # instead, and becomes the one that governs.
    reversed_policy = FsPolicy(binds=(inner, outer))
    assert bwrap.covering_ancestor_bind(reversed_policy, "/custom/level1/level2") == outer
