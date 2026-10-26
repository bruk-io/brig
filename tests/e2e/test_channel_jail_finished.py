"""TASK-0001.30: real bwrap and real procfs for a jail whose command finishes before
`create_bwrap_jail` can look its PID namespace up.

`test_a_jail_whose_command_exits_at_once...` is the AC#2 regression: it ran into a false
`ChannelNamespaceNotFound` before the fix, deterministically, because the in-jail PID 1
(the supervisor) exits with its command and takes bwrap with it. The two scan tests
below use real processes and a real `/proc` rather than a bwrap jail, so they run on
any Linux host; everything here skips on macOS and runs in CI.
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
    ChannelJailFinished,
    await_channel_ready,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
)
from brig.infra import sockets

_NEEDS_BWRAP = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
_NEEDS_PROCFS = pytest.mark.skipif(
    sys.platform != "linux", reason="needs a real /proc; skips on macOS, runs in CI on Linux"
)


@dataclass(frozen=True)
class _DirectoryIn:
    """A `ChannelDirectoryPort` allocating under a test's own directory, with the real
    infra `create`/`remove` behind it (the same shape the readiness battery uses).
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


@_NEEDS_BWRAP
def test_a_jail_whose_command_exits_at_once_is_created_and_reads_as_finished(
    tmp_path: Path,
) -> None:
    """`true` finishes in milliseconds, taking the in-jail PID 1 with it. With a channel
    declared, `create_bwrap_jail` neither raises `ChannelNamespaceNotFound` nor waits out
    its scan deadline, and readiness says the jail finished.
    """
    (tmp_path / "state").mkdir()
    directories = _DirectoryIn(root=str(tmp_path / "state"))
    reserved = reserve_channels((Channel("svc.sock"),), directories=directories)
    (reservation,) = reserved.reservations

    jail = create_bwrap_jail(("true",), channels=reserved, directories=directories)
    try:
        outcome = await_channel_ready(jail, reservation, timeout_s=10.0)
    finally:
        destroy_jail(jail, directories=directories)

    assert jail.channel_namespace_fd is None
    assert outcome == ChannelJailFinished()


def _wait_until_zombie(pid: int) -> None:
    """Block until `pid` has exited without being reaped, so its `/proc` entry reads
    `State: Z` -- the state a jail's outer process is in until `destroy_jail` reaps it.

    Raises:
        AssertionError: `pid` was still not a zombie after 10 s.
    """
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        with open(f"/proc/{pid}/status") as handle:
            if any(line.startswith("State:") and line.split()[1] == "Z" for line in handle):
                return
        time.sleep(0.01)
    raise AssertionError(f"process {pid} never became a zombie")


@_NEEDS_PROCFS
@pytest.mark.parametrize("reaped", [False, True], ids=["zombie", "reaped"])
def test_the_scan_reports_an_exited_outer_process_at_once(reaped: bool) -> None:
    """A real child that has exited -- still a zombie, or already reaped -- is reported
    as `JailPid1Exited` immediately, never by waiting out a 30 s deadline.
    """
    child = subprocess.Popen(["true"])
    _wait_until_zombie(child.pid)
    if reaped:
        child.wait()

    started = time.monotonic()
    outcome = sockets.jail_pid1_namespace(child.pid, time.monotonic() + 30.0)
    child.wait()

    assert isinstance(outcome, sockets.JailPid1Exited)
    assert time.monotonic() - started < 5.0


@_NEEDS_PROCFS
def test_the_scan_still_times_out_when_the_outer_process_runs_with_no_pid1() -> None:
    """The negative control: a live process with no in-jail PID 1 under it stays
    `JailPid1NotFound`, so a genuine creation failure is still `ChannelNamespaceNotFound`.
    """
    child = subprocess.Popen(["sleep", "30"])
    try:
        outcome = sockets.jail_pid1_namespace(child.pid, time.monotonic() + 0.3)
    finally:
        child.kill()
        child.wait()

    assert isinstance(outcome, sockets.JailPid1NotFound)
