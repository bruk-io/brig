"""The host's end of a jail's stdio (TASK-0042): every stream the command gets is a pipe, and one
thread per jail pumps it to or from where the embedder said (a file, or the embedder's own fd).

A jail handed an fd on a host inode can reopen it through `/proc/self/fd/N` with any mode the
file's own permissions allow the same uid, whatever brig opened it with: truncate a stdin file,
read an append-only log. Reopening a pipe reaches only the pipe. Plain data in and out: fds and
deadlines.

The thread never blocks on the jail: its ends of the jail's pipes are non-blocking, and it reads
from a source only once the last chunk is written on. It can block on the embedder's own stream
only where that stream itself blocks (a pipe nobody reads, a stopped terminal), and `finish` does
not wait past its deadline for it.
"""

import os
import select
import signal
import threading
import time
from dataclasses import dataclass

_READ_CHUNK = 65536
"""How many bytes one read from a source takes at most."""

_WRITE_CHUNK = 4096
"""How many bytes one write to a sink gives at most: `PIPE_BUF` on Linux, so a write to a pipe
`poll` reported writable does not block, nor is it split."""

_STOP_GRACE_S = 0.5
"""How long `finish` waits for the thread to stop once its drain deadline passed."""

_DRAIN = b"d"
_STOP = b"s"


@dataclass(frozen=True)
class Flow:
    """One stream: bytes read from `source` are written to `sink`. `inbound` is the command's
    stdin, whose sink is the jail's pipe. Each fd is the flow's own, closed when it ends."""

    source: int
    sink: int
    inbound: bool


def _close(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


class Pumps:
    """The pump thread for one jail's flows.

    Invariant (rule 7): the thread alone reads, writes and closes the flows' fds, and it closes
    each when its flow ends. `_control` is the pipe that tells it to drain or stop, both ends
    open until `finish` has seen the thread end, so telling it never writes to a closed pipe;
    `None` once closed.
    """

    def __init__(self, flows: tuple[Flow, ...]) -> None:
        """Start pumping `flows` on a daemon thread. Each jail-side end (an inbound sink, an
        outbound source) is made non-blocking."""
        for flow in flows:
            os.set_blocking(flow.sink if flow.inbound else flow.source, False)
        self._control: tuple[int, int] | None = os.pipe()
        self._thread = threading.Thread(
            target=_pump, args=(flows, self._control[0]), name="brig-stdio-pumps", daemon=True
        )
        self._thread.start()

    def finish(self, deadline: float) -> None:
        """Stop feeding the command's stdin, pump what the command wrote until its pipes reach end
        of file or `deadline` passes, then stop and close every flow. Safe to call twice."""
        if self._control is None:
            return
        control_read, control_write = self._control
        _tell(control_write, _DRAIN)
        self._thread.join(max(0.0, deadline - time.monotonic()))
        if self._thread.is_alive():
            _tell(control_write, _STOP)
            self._thread.join(_STOP_GRACE_S)
        if not self._thread.is_alive():
            _close(control_read)
            _close(control_write)
            self._control = None


def _tell(control: int, word: bytes) -> None:
    with open(control, "wb", buffering=0, closefd=False) as pipe:
        pipe.write(word)


def _pump(flows: tuple[Flow, ...], control: int) -> None:
    """The thread: move bytes along each of `flows` until every one has ended, or `control`
    says to stop. Told to drain, it ends the inbound flow and keeps the outbound ones to end of
    file. A sink that fails ends an inbound flow (the command closed its stdin); an outbound one
    keeps reading and discards, so the command never blocks on a full pipe.

    `SIGPIPE` is blocked in this thread, so a write to a pipe whose reader is gone fails with
    `EPIPE` here even where the embedder restored the signal's default, which would end it."""
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGPIPE})
    live = {flow.source: flow for flow in flows}
    pending = dict.fromkeys(live, b"")
    discarding: set[int] = set()
    try:
        while live:
            poller = select.poll()
            poller.register(control, select.POLLIN)
            watched: dict[int, int] = {}
            for source, flow in live.items():
                if pending[source]:
                    poller.register(flow.sink, select.POLLOUT)
                    watched[flow.sink] = source
                else:
                    poller.register(source, select.POLLIN)
                    watched[source] = source
            for fd, _ in poller.poll():
                if fd == control:
                    word = os.read(control, 1)
                    if word in (_STOP, b""):
                        return
                    for source in [s for s, flow in live.items() if flow.inbound]:
                        _end(live.pop(source))
                    continue
                source = watched[fd]
                moving = live.get(source)
                if moving is None:
                    continue
                if pending[source]:
                    ended = _write(moving, pending, discarding)
                else:
                    ended = _read(moving, pending, discarding)
                if ended:
                    _end(live.pop(source))
    finally:
        for flow in live.values():
            _end(flow)


def _read(flow: Flow, pending: dict[int, bytes], discarding: set[int]) -> bool:
    """Read the next chunk from `flow`'s source into `pending`; say whether the flow ended."""
    try:
        chunk = os.read(flow.source, _READ_CHUNK)
    except BlockingIOError:
        return False
    except OSError:
        return True
    if not chunk:
        return True
    if flow.source not in discarding:
        pending[flow.source] = chunk
    return False


def _write(flow: Flow, pending: dict[int, bytes], discarding: set[int]) -> bool:
    """Write the next part of `pending` to `flow`'s sink; say whether the flow ended."""
    data = pending[flow.source]
    try:
        with open(flow.sink, "wb", buffering=0, closefd=False) as sink:
            written = sink.write(data[:_WRITE_CHUNK])
    except BlockingIOError:
        return False
    except OSError:
        if flow.inbound:
            return True
        discarding.add(flow.source)
        pending[flow.source] = b""
        return False
    pending[flow.source] = data[written or 0 :]
    return False


def _end(flow: Flow) -> None:
    _close(flow.source)
    _close(flow.sink)
