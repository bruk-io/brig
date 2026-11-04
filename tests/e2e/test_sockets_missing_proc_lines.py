"""TASK-0050: no `StopIteration` escapes `infra/sockets.py` when a `/proc` line is missing.

Two reads take one line with `next(...)`: `channel_ready`'s pidfd `fdinfo` (`Pid:`) and
`jail_pid1_namespace`'s candidate `status` (`NSpid:`). A missing line is each one's documented
outcome: `PEER_LOOKUP_FAILED`, and "this candidate is not the jail's PID 1". The repro of the
second is `test_sockets_nspid_missing.py`; this file holds the cases written after it.

Gateway tests of one `brig.infra` module (decision-0001 rule 4). `channel_ready` connects for
real to a socket this test listens on, so `SO_PEERCRED` and `SO_PEERPIDFD` are the kernel's own;
only the two lookups after them read a procfs-shaped tree planted through `proc_root`, the
module's seam. The pidfd's number is the kernel's choice, the lowest free one, so the fake
`fdinfo` is planted for every number below the highest this process has open plus a margin.
"""

import os
import socket
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from brig.infra import sockets

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="SO_PEERCRED and SO_PEERPIDFD are Linux's (decision-0005 item 7)",
)

_FDINFO_MARGIN = 64
"""How far past this process's highest open fd the fake `fdinfo` is planted: `channel_ready`
opens two fds (the `O_PATH` and the socket) before the pidfd, so a few would do."""


def _plant_fdinfo(proc_root: Path, body: str) -> None:
    """A `<proc_root>/self/fdinfo/<n>` holding `body` for every fd the pidfd could get."""
    fdinfo = proc_root / "self" / "fdinfo"
    fdinfo.mkdir(parents=True)
    highest = max(int(entry) for entry in os.listdir("/proc/self/fd"))
    for number in range(highest + _FDINFO_MARGIN):
        (fdinfo / str(number)).write_text(body)


def _plant_peer_namespace(proc_root: Path, link_text: str) -> None:
    """`<proc_root>/<this pid>/ns/pid` as a link reading `link_text`: the listener is this
    process."""
    ns = proc_root / str(os.getpid()) / "ns"
    ns.mkdir(parents=True)
    (ns / "pid").symlink_to(link_text)


@contextmanager
def _listening(directory: Path) -> Iterator[None]:
    """A socket named `ctl` in `directory`, listened on by this process for the block."""
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(directory / "ctl"))
        listener.listen(8)
        yield
    finally:
        listener.close()


def _ready(
    directory: Path, proc_root: Path
) -> sockets.ChannelReady | sockets.ChannelNotReady | sockets.ChannelRefused:
    """`channel_ready` for `ctl` beneath `directory`, with this process's own PID namespace as
    the jail's and `proc_root` for the peer lookups; every fd it opens is closed again."""
    directory_fd = sockets.open_directory(str(directory))
    namespace_fd = os.open("/proc/self/ns/pid", os.O_RDONLY)
    try:
        outcome = sockets.channel_ready(directory_fd, "ctl", namespace_fd, proc_root=str(proc_root))
    finally:
        os.close(namespace_fd)
        os.close(directory_fd)
    if isinstance(outcome, sockets.ChannelReady):
        outcome.connection.close()
    return outcome


def test_a_pidfd_fdinfo_without_a_pid_line_is_a_lookup_failure(tmp_path: Path) -> None:
    """The listener is real and in this namespace, but the pidfd's `fdinfo` carries no `Pid:`
    line: `channel_ready` refuses with `PEER_LOOKUP_FAILED` rather than raising."""
    proc_root = tmp_path / "proc"
    _plant_peer_namespace(proc_root, os.readlink("/proc/self/ns/pid"))
    _plant_fdinfo(proc_root, "pos:\t0\nflags:\t02000002\nmnt_id:\t15\nino:\t1057\n")

    with _listening(tmp_path):
        outcome = _ready(tmp_path, proc_root)

    assert outcome == sockets.ChannelRefused(sockets.PEER_LOOKUP_FAILED)


def test_the_same_fake_with_the_pid_line_passes(tmp_path: Path) -> None:
    """The positive control: the same planted tree, its `fdinfo` naming this process, passes
    the lookup and is ready, so the refusal above is the missing line's and the seam is read."""
    proc_root = tmp_path / "proc"
    _plant_peer_namespace(proc_root, os.readlink("/proc/self/ns/pid"))
    _plant_fdinfo(proc_root, f"pos:\t0\nflags:\t02000002\nPid:\t{os.getpid()}\nNSpid:\t1\n")

    with _listening(tmp_path):
        outcome = _ready(tmp_path, proc_root)

    assert isinstance(outcome, sockets.ChannelReady)


def _plant_status(proc_root: Path, pid: int, status: str) -> None:
    """A `<proc_root>/<pid>/status` holding `status`, and an empty `ns/pid` to open."""
    entry = proc_root / str(pid)
    (entry / "ns").mkdir(parents=True)
    (entry / "status").write_text(status)
    (entry / "ns" / "pid").write_text("")


def test_the_scan_finds_pid1_beside_a_child_without_an_nspid_line(tmp_path: Path) -> None:
    """A child with no `NSpid:` line and the jail's PID 1 under the same bwrap: whichever the
    listing gives first, the scan skips the one and returns an fd on the other's namespace."""
    proc_root = tmp_path / "proc"
    _plant_status(proc_root, 3000, "Name:\tbwrap\nState:\tS (sleeping)\nPPid:\t1\nNSpid:\t3000\n")
    _plant_status(proc_root, 3001, "Name:\tgoing\nState:\tS (sleeping)\nPPid:\t3000\n")
    _plant_status(
        proc_root, 3002, "Name:\tpid1\nState:\tS (sleeping)\nPPid:\t3000\nNSpid:\t3002\t1\n"
    )

    outcome = sockets.jail_pid1_namespace(3000, time.monotonic() + 1.0, str(proc_root))

    assert isinstance(outcome, int)
    try:
        assert os.fstat(outcome).st_ino == (proc_root / "3002" / "ns" / "pid").stat().st_ino
    finally:
        os.close(outcome)


def test_an_empty_nspid_line_is_skipped_too(tmp_path: Path) -> None:
    """An `NSpid:` line with no pid on it is not the jail's PID 1 either, not an `IndexError`."""
    proc_root = tmp_path / "proc"
    _plant_status(proc_root, 3000, "Name:\tbwrap\nState:\tS (sleeping)\nPPid:\t1\nNSpid:\t3000\n")
    _plant_status(proc_root, 3001, "Name:\tgoing\nState:\tS (sleeping)\nPPid:\t3000\nNSpid:\n")

    outcome = sockets.jail_pid1_namespace(3000, time.monotonic() + 0.2, str(proc_root))

    assert outcome == sockets.JailPid1NotFound()
