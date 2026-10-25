"""TASK-0001.28 AC#2: the `channel_exclusivity` claim, graded from what a real bwrap
jail actually let through -- not from the policy data alone.

`CHANNEL_EXCLUSIVITY_CLAIM` (`domain/jail_types/bwrap.py`) says the only paths a jail
can write that the host can also reach are the channels it declared (old SPEC law 9:
nothing crosses the boundary anonymously). `writable_shared_paths` enumerates what the
compiled argv actually shares; this file is what proves that enumeration corresponds to
something real, by running two real jails through brig's own public API and reading what
they left behind on the host.

Two cases, and the second is why the first means anything:

- **Control**: a jail declaring one channel and nothing else writable. The jailed
  command writes a known string inside its own channel directory; the host reads it back
  after the jail is gone. `writable_shared_paths` on that jail's own
  `policy`/`state_dir`/`channels` returns exactly `declared_channel_paths` -- nothing
  shared beyond the declared channel -- so the claim grades `ENFORCED`.
- **Violation**: the same jail, plus one extra writable `Bind` in its own `FsPolicy`
  pointing at a throwaway host directory that is not a declared channel. The jailed
  command writes into both, and the host reads both back -- proving the extra path is a
  real, exploitable leak rather than a hypothetical one read off the policy. The
  enumeration now returns two paths while `declared_channel_paths` still names one, so
  the claim grades `VIOLATED`: not `UNENFORCED`, because the control did fire and the
  leak was genuinely measured -- `UNENFORCED` would understate what was found.

Guarded to skip cleanly where real bwrap is not available (macOS), the same guard every
other real-jail battery in this suite uses; it runs for real in CI on Linux. A skip is
reported as not run, never counted as a pass.

Each test's channel directory lives under pytest's own throwaway `tmp_path`, through a
`directories` port whose `allocate` names it (`tests/e2e/test_channel_readiness_battery.py`'s
own `_DirectoryIn` shape) -- rather than brig's real state directory, which
`_resolved_state_dir` caches for the life of the process. `create`/`remove` are the real
infra ones, so the directory is genuinely made and genuinely cleaned up.

**Read order matters, and is the correction TASK-0001.28's own plan review caught**:
`destroy_jail` removes the channel directory (`directories.remove`, TASK-0001.26), so the
control's file has to be read back *before* `destroy_jail` runs -- read after, and the
control would report nothing there for a reason having nothing to do with the claim.
The extra bind's own directory sits outside the channel directory and survives
`destroy_jail`, but it is read before too, since there is no reason not to.

TASK-0001.28's own plan named this file and `tests/unit/test_channel_exclusivity_claim.py`
with the same basename, and that collides: `tests/` is a package-less tree
(`pyproject.toml` sets `pythonpath = ["."]`, and no layer directory carries an
`__init__.py`), so pytest 9 imports every test file by its bare basename and refuses two
files with the same one -- `import file mismatch`, whole-session `Interrupted`, not a
failure scoped to either file. Measured: renaming only this file makes the whole suite
collect and run, so this is the collision and nothing else. Fixed by giving the two files
distinct basenames; the plan's own file list is the intent (one unit file, one e2e file),
not a claim about what either may be called.
"""

import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from brig import (
    CHANNEL_EXCLUSIVITY_CLAIM,
    WHOLE_HOST_READ_ONLY,
    Bind,
    Channel,
    Evidence,
    FsPolicy,
    Grade,
    Reservations,
    create_bwrap_jail,
    declared_channel_paths,
    destroy_jail,
    grade,
    reserve_channels,
    writable_shared_paths,
)
from brig.infra import sockets

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_PLANTED_CHANNEL_CONTENT = "brig-channel-exclusivity-control"
"""What the jailed command writes inside its own declared channel directory -- the
positive control: a path the claim says *is* legitimately shared, so a probe that
cannot write even this one is a broken probe, not evidence about the claim.
"""

_PLANTED_EXTRA_CONTENT = "brig-channel-exclusivity-leak"
"""What the jailed command writes through the extra, undeclared writable bind in the
violation case -- distinct from the control's own string, so which write landed where
is never a guess.
"""

_JAILED_PROGRAM = """
import sys, time

channel_path, channel_content, extra_path, extra_content = sys.argv[1:5]

with open(channel_path, "w") as handle:
    handle.write(channel_content)

if extra_path != "-":  # "-" means this jail declares no extra writable bind
    with open(extra_path, "w") as handle:
        handle.write(extra_content)

time.sleep(3600)
"""
"""The jailed command: write the control string inside its own channel directory, then
-- only when the run actually plants one -- write the leak string through the extra
bind, then sleep rather than exit.

Measured, not a style choice: the real command exiting is what lets its own
supervisor -- `program.py`, the jail's in-jail PID 1, decision-0002's own shape --
exit too, immediately after (its own `_main` returns right after emitting the `done`
event over the wire, with nothing left for it to wait on). `create_bwrap_jail` has
already called `infra.sockets.jail_pid1_namespace` to find and hold that same PID 1's
own namespace by the time this process could have written anything at all -- but a
command fast enough to write two small files and exit (measured: real, on
`ubuntu-latest`'s own unprivileged userns runner, never reproduced in a slower,
emulated container) can finish, taking its own supervisor down with it, before that
host-side `/proc` scan ever wins the race to find it -- `ChannelNamespaceNotFound`,
deterministically, no matter how long the scan's own deadline is, since the process
it is looking for is not merely slow to appear, it is already gone. Every other
real-jail battery in this suite already avoids this by construction (a listener loop,
a `time.sleep`, a fork-and-reap command that never finishes on its own) -- this one
needs to avoid it the same way now that it declares channels and goes through the
same `create_bwrap_jail` call that scan lives in. The underlying race is
TASK-0001.27's own design gap, filed separately (its own board task) rather than
"fixed" by a longer timeout here, which this task's own CI run already measured does
not help: the process is gone, not merely late.
"""


@dataclass(frozen=True)
class _DirectoryIn:
    """A `ChannelDirectoryPort` allocating under a test's own directory, with the real
    infra `create`/`remove` behind it -- so the channel directory is a genuine path on
    a genuine filesystem, which real bwrap needs, while still being throwaway rather
    than brig's cached state directory.
    """

    root: str

    def allocate(self) -> str:
        """A fresh, unused path under `root`."""
        return f"{self.root}/channels/run{time.monotonic_ns()}"

    def create(self, path: str) -> None:
        """Make `path` private to the owning user, the real way."""
        sockets.create(path)

    def remove(self, path: str) -> None:
        """Remove `path` and everything in it, the real way."""
        sockets.remove(path)


class _Run:
    """One battery run's own directories: the channel directory's parent, and the
    throwaway host directory the violation case binds writable on top of the policy.
    """

    def __init__(self, root: Path) -> None:
        self.channels = root / "state"
        self.extra = root / "extra"
        self.channels.mkdir(parents=True)
        self.extra.mkdir(parents=True)

    def directories(self) -> _DirectoryIn:
        """The port `reserve_channels`/`create_bwrap_jail` allocate through."""
        return _DirectoryIn(root=str(self.channels))

    def reserve(self) -> Reservations:
        """Reserve one `ctl` channel for this run's jail."""
        return reserve_channels((Channel("ctl"),), directories=self.directories())


@pytest.fixture
def run(tmp_path: Path) -> _Run:
    """A battery run's directories, under pytest's own throwaway `tmp_path`."""
    return _Run(tmp_path)


def _jail_command(channel_path: Path, extra_path: Path | None) -> tuple[str, ...]:
    """The jailed command for one run: the control write always, the leak write only
    when `extra_path` names one (`_JAILED_PROGRAM`'s own "-" convention).
    """
    return (
        sys.executable,
        "-c",
        _JAILED_PROGRAM,
        str(channel_path),
        _PLANTED_CHANNEL_CONTENT,
        str(extra_path) if extra_path is not None else "-",
        _PLANTED_EXTRA_CONTENT,
    )


def _wait_for(path: Path, *, timeout_s: float = 10.0) -> None:
    """Poll until `path` exists, or raise once `timeout_s` passes.

    The jailed command never exits on its own (`_JAILED_PROGRAM`'s own docstring), so
    there is no `run_jail` wait to synchronize on here -- this is the substitute: the
    write this function waits for happens, in the jailed program's own source, before
    the `time.sleep` that keeps the supervisor alive for `_namespace_fd_for`'s scan,
    so a file that exists at all means the write already landed, never a partial one
    this function would need to guard against separately.

    Raises:
        TimeoutError: `path` never appeared before `timeout_s` passed.
    """
    deadline = time.monotonic() + timeout_s
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{path} never appeared")
        time.sleep(0.05)


def _control_path(reserved: Reservations) -> Path:
    """Where a jailed command writes its control string: a file *inside* the channel
    directory the jail declared -- the one path the claim says is legitimately shared
    between the jail and the host, and so the write a probe that works at all must
    land.
    """
    return Path(reserved.directory.host_path) / "control.txt"


def test_a_declared_channel_is_the_only_shared_writable_path_and_that_is_measured(
    run: _Run,
) -> None:
    """The control: a real jail declaring one channel, nothing else writable.

    The shared-path enumeration is computed from this jail's own
    `policy`/`state_dir`/`channels` (never from the compiled argv, parsed back apart)
    and compared against `declared_channel_paths`; the write itself is the independent
    measurement that those paths are real -- the jailed command writes a known string
    into its own channel directory, and the host reads it back, before `destroy_jail`
    removes that directory.
    """
    reserved = run.reserve()
    policy = WHOLE_HOST_READ_ONLY
    channels = reserved
    state_dir = str(run.channels)
    control_path = _control_path(reserved)

    jail = create_bwrap_jail(
        _jail_command(control_path, None),
        channels=reserved,
        directories=run.directories(),
    )
    # The control's own file, written by the jailed command into the directory the
    # claim says is legitimately shared. Waited for, not `run_jail`-synchronized --
    # the command never exits on its own (`_JAILED_PROGRAM`'s own docstring) -- and
    # read before `destroy_jail`: that call removes the whole channel directory
    # (TASK-0001.26), so reading after would report nothing there for a reason that
    # has nothing to do with this claim.
    _wait_for(control_path)
    written = control_path.read_text()
    destroy_jail(jail, directories=run.directories())

    shared = writable_shared_paths(policy, state_dir, channels)
    declared = declared_channel_paths(channels)

    # The write reached the host, through the one path the claim says is shared.
    assert written == _PLANTED_CHANNEL_CONTENT

    # The enumeration agrees with reality: the declared channel directory, and nothing
    # more. So the plant was blocked -- nothing shared beyond what was declared.
    assert shared == declared
    evidence = {CHANNEL_EXCLUSIVITY_CLAIM: Evidence(control_observed=True, violation_blocked=True)}
    assert grade((CHANNEL_EXCLUSIVITY_CLAIM,), evidence) == {
        CHANNEL_EXCLUSIVITY_CLAIM: Grade.ENFORCED
    }


def test_an_undeclared_writable_bind_is_a_real_leak_and_grades_violated(run: _Run) -> None:
    """AC#2's own case: a writable path that is not a declared channel.

    The same jail as the control, plus one extra writable `Bind` in its own `FsPolicy`
    pointing at a throwaway host directory unrelated to any channel. The jailed command
    writes into *both* -- the channel directory (the control signal, so this run also
    proves the probe worked) and the extra bind -- and the host reads both back, so the
    extra path is a genuine, exploitable leak and not merely something the policy names.

    The enumeration now returns two paths while `declared_channel_paths` still names
    one, so the claim grades `VIOLATED`: the control did fire, and the planted extra
    path genuinely was not blocked. `UNENFORCED` would be the wrong word for a leak
    that was actually measured.
    """
    reserved = run.reserve()
    extra_dir = str(run.extra)
    policy = FsPolicy(
        binds=(
            *WHOLE_HOST_READ_ONLY.binds,
            Bind(host_path=extra_dir, jail_path=extra_dir, writable=True),
        )
    )
    channels = reserved
    state_dir = str(run.channels)
    control_path = _control_path(reserved)
    leak_path = Path(extra_dir) / "leak.txt"

    jail = create_bwrap_jail(
        _jail_command(control_path, leak_path),
        policy=policy,
        channels=reserved,
        directories=run.directories(),
    )
    # Waited for, not `run_jail`-synchronized -- the command never exits on its own.
    # Read before `destroy_jail` for the control's own reason (the channel directory is
    # removed there); the extra bind's directory survives that call, but is read here
    # too, so both reads happen at the same point in the jail's life.
    _wait_for(control_path)
    _wait_for(leak_path)
    control_written = control_path.read_text()
    leak_written = leak_path.read_text()
    destroy_jail(jail, directories=run.directories())

    shared = writable_shared_paths(policy, state_dir, channels)
    declared = declared_channel_paths(channels)

    # Both writes reached the host: the control inside the declared channel directory,
    # and the leak through the extra bind -- which is what makes this a real,
    # exploitable leak rather than a name in a policy.
    assert control_written == _PLANTED_CHANNEL_CONTENT
    assert leak_written == _PLANTED_EXTRA_CONTENT
    assert shared == (extra_dir, channels.directory.host_path)
    assert declared == (channels.directory.host_path,)

    evidence = {CHANNEL_EXCLUSIVITY_CLAIM: Evidence(control_observed=True, violation_blocked=False)}
    assert grade((CHANNEL_EXCLUSIVITY_CLAIM,), evidence) == {
        CHANNEL_EXCLUSIVITY_CLAIM: Grade.VIOLATED
    }
