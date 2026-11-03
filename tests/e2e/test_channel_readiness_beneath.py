"""TASK-0045, at infra's edge: `infra/sockets.py`'s `channel_ready` opens the channel's name
beneath a directory fd it is given, through no link, and connects without blocking. Real
sockets and real procfs, nothing faked; decision-0001 rule 4 lets an e2e test import one
`brig.infra` module.

The namespace fd is this test process's own, so a listener this test starts reads ready, which
keeps each other outcome here attributable to what the test planted at the name.
"""

import os
import socket
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from brig.infra import sockets

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="O_PATH and /proc/self/fd are Linux's; test skips on macOS, runs in CI on Linux",
)


@pytest.fixture
def directory(tmp_path: Path) -> Iterator[int]:
    """An fd on `tmp_path`, opened the way a jail's channel directory fd is."""
    fd = sockets.open_directory(str(tmp_path))
    yield fd
    os.close(fd)


@pytest.fixture
def namespace() -> Iterator[int]:
    """An fd on this process's own PID namespace."""
    fd = os.open(f"/proc/{os.getpid()}/ns/pid", os.O_RDONLY)
    yield fd
    os.close(fd)


def _listener(path: Path, backlog: int = 8) -> socket.socket:
    """A socket listening at `path`, held by this process."""
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(backlog)
    return listener


def test_the_ready_connection_is_handed_out_blocking(
    tmp_path: Path, directory: int, namespace: int
) -> None:
    """The connect is made without blocking, but the connection the receiver owns is set back
    to blocking, as `ChannelReady` documents, and is connected to the listener at the name."""
    with _listener(tmp_path / "svc.sock") as listener:
        outcome = sockets.channel_ready(directory, "svc.sock", namespace)
        assert isinstance(outcome, sockets.ChannelReady), outcome
        with outcome.connection as connection:
            assert connection.getblocking()
            assert connection.getpeername() == listener.getsockname()


def test_a_full_backlog_is_not_ready_at_once(
    tmp_path: Path, directory: int, namespace: int
) -> None:
    """A listener with a backlog of 0, filled by one connection nobody accepts, takes no more:
    the attempt is `ChannelNotReady` straight away instead of waiting for room."""
    with _listener(tmp_path / "svc.sock", backlog=0), socket.socket(socket.AF_UNIX) as filler:
        filler.connect(str(tmp_path / "svc.sock"))
        started = time.monotonic()
        outcome = sockets.channel_ready(directory, "svc.sock", namespace)
        elapsed = time.monotonic() - started

    assert outcome == sockets.ChannelNotReady()
    assert elapsed < 0.5


@pytest.mark.parametrize("target", ["listening", "dangling"])
def test_a_link_at_the_name_is_refused_without_a_connect(
    tmp_path: Path, directory: int, namespace: int, target: str
) -> None:
    """A link at the name is `PEER_OUTSIDE_JAIL`, whether it names a live listener (which then
    has no connection waiting) or nothing at all."""
    outside = tmp_path / "outside.sock"
    os.symlink(outside, tmp_path / "svc.sock")
    if target == "dangling":
        outcome = sockets.channel_ready(directory, "svc.sock", namespace)
        assert outcome == sockets.ChannelRefused(sockets.PEER_OUTSIDE_JAIL)
        return
    with _listener(outside) as listener:
        outcome = sockets.channel_ready(directory, "svc.sock", namespace)
        listener.setblocking(False)
        with pytest.raises(BlockingIOError):
            listener.accept()

    assert outcome == sockets.ChannelRefused(sockets.PEER_OUTSIDE_JAIL)


def test_anything_but_a_socket_or_a_link_is_not_ready(
    tmp_path: Path, directory: int, namespace: int
) -> None:
    """A regular file, a directory and nothing at all are each `ChannelNotReady`: transient,
    as a name the jail has not bound yet is."""
    (tmp_path / "file").write_text("not a socket")
    (tmp_path / "dir").mkdir()

    for name in ("file", "dir", "absent"):
        assert sockets.channel_ready(directory, name, namespace) == sockets.ChannelNotReady()


def test_the_lookup_is_beneath_the_held_directory_not_its_path(
    tmp_path: Path, namespace: int
) -> None:
    """The fd names the directory it was opened on: once that directory has been moved away
    and another put at its path, a listener in the new one is not what the name reaches."""
    held = tmp_path / "channels"
    held.mkdir()
    fd = sockets.open_directory(str(held))
    try:
        held.rename(tmp_path / "moved")
        held.mkdir()
        with _listener(held / "svc.sock"):
            outcome = sockets.channel_ready(fd, "svc.sock", namespace)
    finally:
        os.close(fd)

    assert outcome == sockets.ChannelNotReady()
