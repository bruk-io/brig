"""E2E gateway battery for `infra.processes.spawn`'s `fds` redirection (TASK-0005).

Decision-0001 rule 4 lets an e2e test import one `brig.infra` module directly, for
exactly this: a real fd-allocation hazard against the real OS, with nothing faked
and no bwrap needed.

`spawn`'s `fds` redirects some of its own fds onto the new process's fd numbers
(`infra/supervisor/link.py` uses this for `wire.REQUEST_FD`/`EVENTS_FD`). A source
fd that collides with one of `fds`'s own target numbers is relocated first
(`_resolve_fd_sources`) -- but relocating it with a bare `os.dup` picks this
process's *lowest* free fd, which is itself a target number whenever this process
happens to have a hole there. `_fd_actions` then closed that relocated number
unconditionally, which -- when it collided with another pair's own target -- undid
that pair's `DUP2` before `argv[0]` ever ran.

Forces the exact allocation TASK-0005 measured: one target's source is itself (the
common case an unencumbered process hits on its very first `os.pipe()`), and the
other target's own number is a hole, freed and made this process's lowest free fd,
right before the colliding source is relocated. The first `os.pipe()` call returns
this process's two lowest free fds, so every number up to and including
`request_write_fd` is open; closing `request_write_fd` then makes that number this
process's new lowest free fd, by the same POSIX guarantee, right before the
colliding source is relocated onto it. (The second `os.pipe()` call's own numbers
play no part in this: POSIX only guarantees each call returns the lowest free pair
*at that moment* -- nothing holds the two calls' own four numbers consecutive if
something else has an fd open in between, and nothing here needs them to be.)
"""

import os
import sys

from brig.infra.processes import reap, spawn

_STDIO_FDS = (0, 1, 2)
"""The allow-list the probe spawn below grants beyond the two fds under test."""

_EVENTS_PAYLOAD = b"relocated-ok"
"""What the probe writes to its redirected fd -- read back by this test to confirm
that fd is still the real channel `spawn` was asked to put there, not closed out
from under it.
"""

_EVENTS_PROBE = f"""
import os, sys
os.write(int(sys.argv[1]), {_EVENTS_PAYLOAD!r})
"""
"""Writes `_EVENTS_PAYLOAD` to the fd number its own argv names, then exits -- the
probe's whole job, so a `Bad file descriptor` from a clobbered fd surfaces as an
uncaught `OSError` (a nonzero exit), not a silent gap in what this test reads back.
"""


def test_spawn_does_not_clobber_a_redirected_fd_whose_relocated_source_lands_on_a_target() -> None:
    """TASK-0005 AC#1/AC#2: a source fd relocated out of a collision must never
    land on `fds`'s own target numbers, and a `CLOSE` action must never undo the
    `DUP2` that wrote a target onto one.

    Builds the exact shape TASK-0005 measured: `target_request`'s own source is
    itself (self-collision, the common case), and `target_events`'s number is a
    hole this test freed and made the process's lowest free fd right before the
    colliding source would be relocated. Against the pre-fix code, the relocated
    source lands on `target_events` and is then closed, so the probe's `os.write`
    to it fails and nothing arrives on `events_read_fd`; against the fix, the
    probe's payload arrives unchanged.
    """
    request_read_fd = request_write_fd = events_read_fd = events_write_fd = -1
    process_pid: int | None = None
    try:
        request_read_fd, request_write_fd = os.pipe()
        events_read_fd, events_write_fd = os.pipe()
        target_events = request_write_fd
        os.close(request_write_fd)  # the sole hole: freed, and this process's lowest free fd
        request_write_fd = -1

        target_request = request_read_fd
        process = spawn(
            (sys.executable, "-c", _EVENTS_PROBE, str(target_events)),
            _STDIO_FDS,
            fds={target_request: request_read_fd, target_events: events_write_fd},
        )
        process_pid = process.pid

        os.close(events_write_fd)
        events_write_fd = -1
        received = os.read(events_read_fd, 4096)
        exit_code = reap(process.pid)
    finally:
        for fd in (request_read_fd, request_write_fd, events_read_fd, events_write_fd):
            if fd >= 0:
                os.close(fd)

    assert exit_code == 0, f"probe did not exit cleanly (pid={process_pid}): {exit_code!r}"
    assert received == _EVENTS_PAYLOAD
