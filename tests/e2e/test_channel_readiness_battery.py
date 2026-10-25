"""TASK-0001.27 AC#2: the readiness battery, against real bwrap, through brig's own
public API -- `reserve_channels`, `create_bwrap_jail`, `await_channel_ready`,
`destroy_jail`. Nothing here is faked or patched: the jail, its PID namespace, and the
procfs that namespace is scanned out of are all the real ones.

Three cases, and the third is what makes the other two mean anything:

- the jail's own listener at the reserved path reads ready;
- a reserved path the *jail itself* symlinked to a listener outside the jail is
  refused -- TASK-0001.24's planted confused deputy, the shape old SPEC decision-185
  recorded a co-tenant performing, and the only case that proves the `/proc` child
  scan happened at all rather than bwrap's own (host) namespace being compared with
  itself;
- a reserved path with nothing listening is not ready, and stays not ready to the
  deadline -- so a run cannot pass by refusing everything.

Guarded to skip cleanly where real bwrap is not available (macOS), the same guard
`tests/e2e/test_bwrap_journey.py` uses; it runs for real in CI on Linux. A skip is
reported as not run, never counted as a pass.

Each test's channel directory lives under pytest's own throwaway `tmp_path`, through a
`directories` port whose `allocate` names it -- rather than brig's real state
directory, which `_resolved_state_dir` caches for the life of the process. The port's
`create`/`remove` are the real infra ones, so the directory is genuinely made and
genuinely cleaned up.
"""

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from brig import (
    Channel,
    ChannelNotReady,
    ChannelReadinessRefusal,
    ChannelReady,
    ChannelRefused,
    Reservation,
    Reservations,
    await_channel_ready,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
)
from brig.infra import sockets

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_JAILED_PROGRAM = r"""
import os, socket, sys, time

mode, path, outside = sys.argv[1], sys.argv[2], sys.argv[3]


def serve(where):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(where)
    listener.listen(8)
    while True:
        connection, _ = listener.accept()
        connection.close()


pid = os.fork()
if pid == 0:
    if mode == "own":
        serve(path)
    elif mode == "plant-symlink":
        os.symlink(outside, path)
        time.sleep(3600)
    os._exit(0)
while True:
    try:
        os.wait()
    except ChildProcessError:
        time.sleep(3600)
"""
"""The jailed program, adapted from TASK-0001.24's own `JAIL_PROGRAM`: in-jail PID 1
forks the real listener as a descendant (the shape a supervised command has) and then
reaps, so the listener is never itself PID 1 -- which is what the namespace scan roots
at, and what makes this battery exercise the scan rather than a process that happens
to be the one it looks for.

`mode` is what the jail does with its reserved path: `own` binds a real listener at it;
`plant-symlink` makes it a symlink to `outside`, a socket a process outside the jail is
listening on. Both then stay running, so the connection has something to answer it.
"""

_OUTSIDE_LISTENER = r"""
import socket, sys
listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
listener.bind(sys.argv[1])
listener.listen(8)
print("up", flush=True)
while True:
    connection, _ = listener.accept()
    connection.close()
"""
"""A listener this test host holds open outside any jail: the co-tenant that plants the
confused deputy, standing in for old SPEC decision-185's own.
"""


@dataclass(frozen=True)
class _DirectoryIn:
    """A `ChannelDirectoryPort` that allocates under a test's own directory, with the
    real infra `create`/`remove` behind it -- so the channel directory is a genuine
    path on a genuine filesystem, which is what real bwrap needs, while still being
    throwaway rather than brig's cached state directory.
    """

    root: str

    def allocate(self) -> str:
        """A fresh, unused path under `root`."""
        return os.path.join(self.root, "channels", f"run{time.monotonic_ns()}")

    def create(self, path: str) -> None:
        """Make `path` private to the owning user, the real way."""
        sockets.create(path)

    def remove(self, path: str) -> None:
        """Remove `path` and everything in it, the real way."""
        sockets.remove(path)


class _Run:
    """One battery run's own directories: the channel directory's parent, and a
    directory the jail is given no write access to, holding the outside listener.
    """

    def __init__(self, root: Path) -> None:
        self.channels = root / "state"
        self.outside = root / "outside"
        self.channels.mkdir(parents=True)
        self.outside.mkdir(parents=True)

    def directories(self) -> _DirectoryIn:
        """The port `reserve_channels`/`create_bwrap_jail` allocate through."""
        return _DirectoryIn(root=str(self.channels))

    def reserve(self) -> tuple[Reservations, Reservation]:
        """Reserve one `svc.sock`, and hand back both the `Reservations`
        `create_bwrap_jail` takes and the single reservation readiness is asked about.
        """
        reserved = reserve_channels((Channel("svc.sock"),), directories=self.directories())
        (reservation,) = reserved.reservations
        return reserved, reservation

    def start_outside_listener(self) -> subprocess.Popen[bytes]:
        """Start the outside listener and wait until it reports itself up, so the test
        never races its own fixture.
        """
        process = subprocess.Popen(
            [sys.executable, "-c", _OUTSIDE_LISTENER, str(self.outside / "host.sock")],
            stdout=subprocess.PIPE,
        )
        assert process.stdout is not None
        assert process.stdout.readline() == b"up\n"
        return process


@pytest.fixture
def run(tmp_path: Path) -> _Run:
    """A battery run's directories, under pytest's own throwaway `tmp_path`."""
    return _Run(tmp_path)


def test_a_jail_listening_on_its_own_reserved_path_reads_ready(run: _Run) -> None:
    """The positive control: the jailed program's own listener sits in the jail's own
    PID namespace, so readiness reports ready. Without this, a check that refused
    everything would still pass the confused-deputy case below.
    """
    reserved, reservation = run.reserve()
    jail = create_bwrap_jail(
        (sys.executable, "-c", _JAILED_PROGRAM, "own", reservation.endpoint, "unused"),
        channels=reserved,
        directories=run.directories(),
    )
    try:
        outcome = await_channel_ready(jail, reservation, timeout_s=10.0)
    finally:
        destroy_jail(jail)

    assert outcome == ChannelReady()


def test_a_reserved_path_symlinked_to_an_outside_listener_is_refused(run: _Run) -> None:
    """TASK-0001.27 AC#2, the planted confused deputy (old SPEC decision-185): the
    jail itself symlinks its reserved path to a socket a process outside the jail is
    listening on. The path exists and the connect succeeds, so a path-existence check
    would report ready -- the refusal has to come from the answering peer's PID
    namespace, and `PEER_OUTSIDE_JAIL` is that answer.
    """
    outside = run.start_outside_listener()
    reserved, reservation = run.reserve()
    jail = create_bwrap_jail(
        (
            sys.executable,
            "-c",
            _JAILED_PROGRAM,
            "plant-symlink",
            reservation.endpoint,
            str(run.outside / "host.sock"),
        ),
        channels=reserved,
        directories=run.directories(),
    )
    try:
        outcome = await_channel_ready(jail, reservation, timeout_s=10.0)
    finally:
        destroy_jail(jail)
        outside.kill()
        outside.wait()

    assert outcome == ChannelRefused(ChannelReadinessRefusal.PEER_OUTSIDE_JAIL)


def test_a_reserved_path_with_nothing_listening_is_never_ready(run: _Run) -> None:
    """The other control: a path that exists with no listener behind it is not ready,
    and stays not ready for as long as it is polled -- `ChannelNotReady`, never a
    refusal and never a ready. This is what keeps the two cases above from being
    satisfied by a check that only ever says one thing.
    """
    reserved, reservation = run.reserve()
    # `reserve_channels` only names the directory (its own docstring: a refused
    # name must never have created anything) -- `create_bwrap_jail` is what
    # actually creates it, later. This stand-in file needs the directory to exist
    # first, so this test makes it the same way `create_bwrap_jail` itself would.
    run.directories().create(reserved.directory.host_path)
    Path(reservation.bound_path).write_text("stand-in for a socket nobody listens on")
    jail = create_bwrap_jail(
        (sys.executable, "-c", "import time\ntime.sleep(3600)"),
        channels=reserved,
        directories=run.directories(),
    )
    started = time.monotonic()
    try:
        outcome = await_channel_ready(jail, reservation, timeout_s=1.0)
    finally:
        destroy_jail(jail)

    assert outcome == ChannelNotReady()
    assert time.monotonic() - started >= 1.0


def test_the_jail_namespace_is_not_the_bwrap_processs_own(run: _Run) -> None:
    """The fact the whole mechanism rests on, asserted against the real world: the fd
    `create_bwrap_jail` put on the `Jail` names a PID namespace, and it is *not* the
    one bwrap itself is in.

    This is the shortcut the task exists to rule out. Comparing a peer against
    `Jail.process.pid`'s own namespace would compare the host's namespace with itself
    and read every peer as inside the jail -- and every other test in this file would
    still pass. TASK-0001.24 measured the two apart on real bwrap
    (`bwrap=9 ns=pid:[4026532557]`, the probe host's own, against the in-jail PID 1's
    `ns=pid:[4026532693]`).
    """
    reserved, reservation = run.reserve()
    jail = create_bwrap_jail(
        (sys.executable, "-c", _JAILED_PROGRAM, "own", reservation.endpoint, "unused"),
        channels=reserved,
        directories=run.directories(),
    )
    try:
        assert jail.channel_namespace_fd is not None
        jail_namespace = os.readlink(f"/proc/self/fd/{jail.channel_namespace_fd}")
        bwrap_namespace = os.readlink(f"/proc/{jail.process.pid}/ns/pid")
    finally:
        destroy_jail(jail)

    assert jail_namespace.startswith("pid:[")
    assert bwrap_namespace.startswith("pid:[")
    assert jail_namespace != bwrap_namespace
