"""TASK-0046, `infra.supervisor.link`'s half: a start that fails after the supervisor was
spawned hands the spawned supervisor back on its `SupervisorSpawnError`, still running and
unreaped, for the caller's verified teardown. It used to wait for it to exit (`waitpid`, no
signal), so a supervisor that closed its request pipe and lived on held the start, and nothing
told the caller there was a process to tear down.

A gateway test against the real spawn: the supervisor is a stand-in shell that closes its
`wire.REQUEST_FD` and sleeps, and the exec request is larger than a pipe holds, so the write is
still blocked when the reader goes and fails with `EPIPE` every time, with no race.
"""

import os
import signal
import time

import pytest

from brig.infra.supervisor import link, wire


def test_a_request_that_cannot_be_written_hands_back_the_spawned_supervisor() -> None:
    """The start raises at once with the stand-in's `(pid, pgid)`, and the stand-in is still
    running and still this process's child, to be torn down by the caller."""
    stand_in = ("/bin/sh", "-c", f"exec {wire.REQUEST_FD}<&-; exec sleep 30")
    live = link.LiveSupervisor(stand_in)
    began = time.monotonic()

    with pytest.raises(link.SupervisorSpawnError) as raised:
        live.start(("true",), {"FILL": "x" * 200_000})

    spawned = raised.value.spawned
    assert spawned is not None
    pid, pgid = spawned
    try:
        assert time.monotonic() - began < 10
        assert pgid == pid
        assert os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None
    finally:
        os.killpg(pgid, signal.SIGKILL)
        os.waitpid(pid, 0)
