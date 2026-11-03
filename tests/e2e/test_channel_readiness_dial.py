"""TASK-0045's repro, against real bwrap through brig's public API: readiness's own dial.

- **(a) the deadline.** The jail listens with a backlog of 0 and fills it itself with one
  connection it never accepts, so nothing it listens on will take another. `await_channel_ready`
  with `timeout_s=2` must come back within the deadline and a small bound, with an outcome that
  is not ready; a blocking connect waits on the full backlog and ignores the deadline (law 7).
- **(b) the planted link.** The jail makes the reserved name a symbolic link to a socket this
  test listens on outside the jail. Readiness must refuse it without the embedder connecting to
  what the link names; a connect that follows the link lands in that listener's backlog, which
  this test reads afterwards. A connection there would have reached a host service as the
  embedder (a socket-activated one starts on it).

Each jail signals the state it set up by writing a marker into its channel directory, so the
test asks for readiness only once that state is in place.
"""

import os
import shutil
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from brig import (
    Channel,
    ChannelNotReady,
    ChannelReady,
    ChannelRefused,
    Jail,
    Reservation,
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

_FILLED_BACKLOG = r"""
import os, socket, sys, time

path = sys.argv[1]
listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
listener.bind(path)
listener.listen(0)
held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
held.connect(path)
filler = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
filler.setblocking(False)
try:
    filler.connect(path)
    sys.exit(3)
except BlockingIOError:
    pass
with open(os.path.join(os.path.dirname(path), "marker"), "w") as handle:
    handle.write("full")
time.sleep(3600)
"""
"""Listens at the reserved path with a backlog of 0, connects to itself once and never
accepts, checks that a further non-blocking connect is refused for a full backlog, and only
then writes the marker."""

_PLANTED_LINK = r"""
import os, sys, time

path, outside = sys.argv[1], sys.argv[2]
os.symlink(outside, path)
with open(os.path.join(os.path.dirname(path), "marker"), "w") as handle:
    handle.write("linked")
time.sleep(3600)
"""
"""Makes the reserved path a symbolic link to `outside`, then writes the marker."""

_DEADLINE_S = 2.0
_BOUND_S = 2.0
"""How far past its deadline readiness may come back: a few attempts' worth, far under the
time a blocking connect waits."""


@dataclass(frozen=True)
class _DirectoryIn:
    """A `ChannelDirectoryPort` under a test's own directory, with infra's real `create` and
    `remove` behind it."""

    root: str

    def allocate(self) -> str:
        """A fresh path under `root`."""
        return os.path.join(self.root, f"run{time.monotonic_ns()}")

    def create(self, path: str) -> None:
        """Make `path` private to the owning user, the real way."""
        sockets.create(path)

    def remove(self, path: str) -> None:
        """Remove `path` and everything in it, the real way."""
        sockets.remove(path)


def _jail(tmp_path: Path, program: str, *extra: str) -> tuple[Jail, Reservation, _DirectoryIn]:
    """A jail running `program` with its one reservation's endpoint and `extra` as arguments,
    once its marker is written."""
    directories = _DirectoryIn(str(tmp_path / "state"))
    reserved = reserve_channels((Channel("svc.sock"),), directories=directories)
    (reservation,) = reserved.reservations
    jail = create_bwrap_jail(
        (sys.executable, "-c", program, reservation.endpoint, *extra),
        channels=reserved,
        directories=directories,
    )
    marker = Path(reserved.directory.host_path) / "marker"
    deadline = time.monotonic() + 10.0
    while not marker.exists():
        if time.monotonic() > deadline:
            destroy_jail(jail, directories=directories)
            pytest.fail("the jail never wrote its marker")
        time.sleep(0.05)
    return jail, reservation, directories


def test_readiness_honours_its_deadline_against_a_full_backlog(tmp_path: Path) -> None:
    """(a): with the jail's backlog full and nothing accepting, readiness returns within the
    deadline plus a small bound, and does not read ready."""
    jail, reservation, directories = _jail(tmp_path, _FILLED_BACKLOG)
    outcomes: list[object] = []
    waiter = threading.Thread(
        target=lambda: outcomes.append(
            await_channel_ready(jail, reservation, timeout_s=_DEADLINE_S)
        ),
        daemon=True,
    )
    started = time.monotonic()
    try:
        waiter.start()
        waiter.join(_DEADLINE_S + _BOUND_S)
        elapsed = time.monotonic() - started
        finished = not waiter.is_alive()
    finally:
        destroy_jail(jail, directories=directories)
        waiter.join(10.0)
        for outcome in outcomes:
            if isinstance(outcome, ChannelReady):
                outcome.connection.close()

    assert finished, f"await_channel_ready was still blocked after {elapsed:.1f} s"
    assert len(outcomes) == 1
    assert not isinstance(outcomes[0], ChannelReady), outcomes[0]


def test_a_planted_link_is_refused_without_dialling_what_it_names(tmp_path: Path) -> None:
    """(b): the reserved name is a link to a host listener; readiness refuses it, and that
    listener has no connection waiting."""
    outside = tmp_path / "outside"
    outside.mkdir()
    host = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    host.bind(str(outside / "host.sock"))
    host.listen(8)
    try:
        jail, reservation, directories = _jail(tmp_path, _PLANTED_LINK, str(outside / "host.sock"))
        try:
            outcome = await_channel_ready(jail, reservation, timeout_s=_DEADLINE_S)
        finally:
            destroy_jail(jail, directories=directories)
        if isinstance(outcome, ChannelReady):
            outcome.connection.close()
        host.setblocking(False)
        try:
            dialled, _ = host.accept()
        except BlockingIOError:
            dialled = None
        if dialled is not None:
            dialled.close()
    finally:
        host.close()

    assert isinstance(outcome, ChannelRefused | ChannelNotReady), outcome
    assert dialled is None, "the host listener behind the link was dialled"
    assert isinstance(outcome, ChannelRefused), outcome
