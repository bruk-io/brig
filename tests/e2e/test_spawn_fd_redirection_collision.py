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
right before the colliding source is relocated. `_fill_fd_holes_below` first closes
off every lower candidate this pytest process itself happens to carry, so which fd
`os.dup` would pick is this test's choice, not whatever this run's own fd table
left behind -- the same reasoning `test_spawn_close_action_race.py`'s calibration
already applies to a different hazard in this same function.
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


def _fill_fd_holes_below(limit: int) -> list[int]:
    """Dup fd `0` onto every closed fd number in `[3, limit)`, and return the
    numbers filled so the caller can close them again once the test is done.

    Leaves this test free to force a hole at one specific, chosen number without
    some other, lower hole already in this pytest process's own fd table (capture
    fds, plugin sockets, anything else already closed below `limit`) stealing the
    next `os.dup`/`os.pipe` allocation instead.
    """
    filled: list[int] = []
    for fd in range(3, limit):
        try:
            os.fstat(fd)
        except OSError:
            os.dup2(0, fd)
            filled.append(fd)
    return filled


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
    probe_fd = os.dup(0)
    next_fd = probe_fd
    os.close(probe_fd)
    filled = _fill_fd_holes_below(next_fd)

    request_read_fd = request_write_fd = events_read_fd = events_write_fd = -1
    process_pid: int | None = None
    try:
        request_read_fd, request_write_fd = os.pipe()
        events_read_fd, events_write_fd = os.pipe()
        os.close(request_write_fd)  # the sole hole: freed, and this process's lowest free fd

        target_request = request_read_fd
        target_events = request_write_fd
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
                try:
                    os.close(fd)
                except OSError:
                    pass
        for fd in filled:
            os.close(fd)

    assert exit_code == 0, f"probe did not exit cleanly (pid={process_pid}): {exit_code!r}"
    assert received == _EVENTS_PAYLOAD
