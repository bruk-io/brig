"""TASK-0001.27 AC#4 and AC#5: `infra/sockets.py`'s `channel_ready` against real
sockets and real procfs. Decision-0001 rule 4 lets an e2e test import a `brig.infra`
module directly, the same allowance `test_sockets_gateway.py` uses; these are e2e
tests rather than integration ones because what is under test is the syscall sequence
itself -- a real listening peer, a real `SO_PEERCRED`/`SO_PEERPIDFD` read, and real
`/proc`. Nothing is patched, so what is pinned here is what the host's own kernel
does.

AC#4: every `OSError` the peer lookup can reach is a refusal *value*, never raised out
of the primitive and never a fallback to the bare `SO_PEERCRED` pid -- including the
measured `EINVAL` from `SO_PEERPIDFD` on a peer that exited and was reaped while its
child kept the socket. AC#5: a kernel without `SO_PEERPIDFD` refuses with a typed
reason rather than degrading to `SO_PEERCRED` alone.

Both are Linux-only: there is no `/proc`, no `SO_PEERPIDFD`, and no `unshare` on this
project's macOS development host, so the module skips cleanly there and runs for real
in CI. A skip is reported as not run, never counted as a pass.

Nothing here needs bwrap: the namespace fd is this test's own process's, so a peer in
this process's namespace reads ready -- which is what keeps the refusal cases
attributable to the failure each test arranges rather than to a namespace mismatch.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from brig.infra import sockets

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or shutil.which("unshare") is None,
    reason=(
        "peer-lookup refusals need Linux procfs and unshare; test skips on macOS, "
        "runs in CI on Linux"
    ),
)

_LISTENER = r"""
import socket, sys
listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
listener.bind(sys.argv[1])
listener.listen(8)
print("up", flush=True)
while True:
    connection, _ = listener.accept()
    connection.close()
"""
"""A listener a test drives: it binds `argv[1]`, reports itself up, then accepts. Run
as a child process, so the peer is a *different* process from the one calling
`channel_ready` -- `SO_PEERPIDFD` names the listen() caller, and a process cannot be
its own peer here.
"""

_REAPED_LISTENER = r"""
import os, socket, sys, time
listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
listener.bind(sys.argv[1])
listener.listen(8)
keeper_pid = os.fork()
if keeper_pid == 0:
    time.sleep(60)
    os._exit(0)
print(keeper_pid, flush=True)
"""
"""The listen() caller for `test_a_reaped_listen_caller_refuses_rather_than_raising`:
binds and listens, forks a "keeper" that inherits the listening fd and just holds it
open, prints the keeper's pid, and exits -- this script's own process is "the listen()
caller" the kernel will remember for this socket, and it is gone by the time the test
reads its own exit status. The keeper is reparented (to this container's pid 1, absent
a subreaper) rather than to the test process, so the test cleans it up by pid, not by
`waitpid`.
"""


class _Peer:
    """A real listening child process, torn down whichever way a test leaves it."""

    def __init__(self, sock_path: str) -> None:
        self.path = sock_path
        self.process = subprocess.Popen(
            [sys.executable, "-c", _LISTENER, sock_path],
            stdout=subprocess.PIPE,
        )
        assert self.process.stdout is not None
        assert self.process.stdout.readline() == b"up\n"

    def stop(self) -> None:
        """Kill the listener and reap it, so no zombie is left behind."""
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        if self.process.stdout is not None:
            self.process.stdout.close()


@pytest.fixture
def peer(tmp_path: Path) -> Iterator[_Peer]:
    """A real listening child process at a path under pytest's throwaway `tmp_path`."""
    listening = _Peer(str(tmp_path / "svc.sock"))
    yield listening
    listening.stop()


def _only_child(pid: int) -> int:
    """`pid`'s one direct child, found by scanning `/proc` for a matching `PPid`
    line.

    `unshare --pid --fork CMD` calls `unshare(CLONE_NEWPID)` and *then* forks `CMD`
    as its own child: the calling `unshare` process named by `subprocess.Popen`'s own
    pid is not itself moved into the new namespace (`man unshare(2)`) -- only a
    child created after the call is, the same wrapper/inner-process split
    `infra.sockets.jail_pid1_namespace` already measures for bwrap's own `--as-pid-1`.
    Reading `self.process.pid`'s own `ns/pid` directly, without this scan, measures
    the *original* namespace a second time and makes this fixture indistinguishable
    from `_own_namespace_fd` -- the bug this scan exists to not repeat.

    Raises:
        RuntimeError: no child of `pid` appeared before a 5-second deadline passed.
    """
    deadline = time.monotonic() + 5.0
    while True:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/status") as handle:
                    if any(
                        line.startswith("PPid:") and int(line.split()[1]) == pid for line in handle
                    ):
                        return int(entry)
            except OSError:
                continue
        if time.monotonic() > deadline:
            raise RuntimeError(f"no child of {pid} appeared")
        time.sleep(0.05)


class _DifferentNamespace:
    """A live process in its own PID namespace, and an open fd on that namespace.

    The fd has to come off a real `/proc` entry for a process that is genuinely
    inside the namespace -- that is exactly what `jail_pid1_namespace` hands back --
    so this starts one and holds it open rather than manufacturing a link.
    """

    def __init__(self) -> None:
        self.process = subprocess.Popen(
            ["unshare", "--user", "--map-root-user", "--pid", "--fork", "sleep", "3600"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # `self.process.pid` names the `unshare` wrapper, still in *this* process's
        # own namespace -- `_only_child` finds `sleep`, the process `--fork` actually
        # placed inside the new one.
        inner_pid = _only_child(self.process.pid)
        self.fd = os.open(f"/proc/{inner_pid}/ns/pid", os.O_RDONLY)

    def close(self) -> None:
        os.close(self.fd)
        self.process.kill()
        self.process.wait()


def _own_namespace_fd() -> int:
    """An open fd on this process's own PID namespace: the stand-in for a jail's
    namespace fd, with the peer a test starts sitting inside it.
    """
    return os.open(f"/proc/{os.getpid()}/ns/pid", os.O_RDONLY)


def test_a_peer_in_the_same_namespace_reads_ready(peer: _Peer) -> None:
    """The control every refusal below is read against: a real peer, in this process's
    own namespace, reads ready. Without it, a `channel_ready` that refused everything
    would satisfy the rest of this file.
    """
    namespace_fd = _own_namespace_fd()
    try:
        outcome = sockets.channel_ready(peer.path, namespace_fd)
    finally:
        os.close(namespace_fd)

    assert outcome == sockets.ChannelReady()


def test_a_peer_in_a_different_namespace_is_refused(peer: _Peer) -> None:
    """The comparison the check exists to make: the same real peer, checked against a
    namespace fd naming *another* PID namespace, is refused as outside the jail.
    """
    other = _DifferentNamespace()
    try:
        outcome = sockets.channel_ready(peer.path, other.fd)
    finally:
        other.close()

    assert outcome == sockets.ChannelRefused(sockets.PEER_OUTSIDE_JAIL)


def test_channel_ready_never_raises_for_a_path_with_no_listener(tmp_path: Path) -> None:
    """AC#4's floor: nothing at the path is `ChannelNotReady`, a value -- a failed
    connect is an ordinary outcome here and never escapes as an exception.
    """
    namespace_fd = _own_namespace_fd()
    try:
        outcome = sockets.channel_ready(str(tmp_path / "never-created"), namespace_fd)
    finally:
        os.close(namespace_fd)

    assert outcome == sockets.ChannelNotReady()


def test_a_reaped_listen_caller_refuses_rather_than_raising(tmp_path: Path) -> None:
    """AC#4's measured case: a listen() caller that exits and is reaped while its
    child keeps the socket open makes `SO_PEERPIDFD` raise `EINVAL` -- both of
    TASK-0001.24's skeptics measured it, and the spike's own probe let that error
    escape.

    The answer must be a refusal, and `PEER_LOOKUP_FAILED`: not `KERNEL_UNSUPPORTED`,
    which would blame the kernel for a peer that genuinely could not be identified,
    and not a bare `SO_PEERCRED` pid, which is the fallback AC#4 forbids.

    `_REAPED_LISTENER` runs as its own subprocess so that *it*, not this test
    process, is the one whose exit and reap this test actually waits on -- an
    earlier version of this test forked a throwaway child right here instead, which
    left this test process itself as the live, never-exited listen() caller, so
    every lookup legitimately read `ChannelReady()`: a refusal that never had
    anything to refuse.
    """
    listener_path = str(tmp_path / "svc.sock")
    caller = subprocess.Popen(
        [sys.executable, "-c", _REAPED_LISTENER, listener_path], stdout=subprocess.PIPE
    )
    assert caller.stdout is not None
    keeper_pid = int(caller.stdout.readline())
    caller.wait()  # the listen() caller has now exited and is reaped
    time.sleep(0.1)  # let the kernel finish tearing its task down

    namespace_fd = _own_namespace_fd()
    try:
        outcome = sockets.channel_ready(listener_path, namespace_fd)
    finally:
        os.close(namespace_fd)
        caller.stdout.close()
        # The keeper was reparented away from this process (no subreaper set), so
        # there is no pid of ours left to `waitpid` -- best-effort kill only.
        try:
            os.kill(keeper_pid, signal.SIGKILL)
        except OSError:
            pass

    assert outcome == sockets.ChannelRefused(sockets.PEER_LOOKUP_FAILED)
