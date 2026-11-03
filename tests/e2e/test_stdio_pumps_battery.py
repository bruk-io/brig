"""TASK-0042 AC#3: the pumps that carry a jail's stdio end with the jail (law 7), against real
bwrap. A jail that never reads its stdin, or floods its stdout, does not hold the host past
`destroy_jail`; what a command wrote before it exited is in the file when `run_jail` returns;
and no fd of the host's is left open once the jail is gone.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from brig import Stdio, create_bwrap_jail, destroy_jail, run_jail

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_BOUND_S = 8.0
"""How long `destroy_jail` may take here: its kill ladder and the pumps' drain, with room."""


def _open_fds() -> int:
    return len(os.listdir("/proc/self/fd"))


def _wait_for_size(path: Path, size: int) -> None:
    deadline = time.monotonic() + 10
    while path.stat().st_size < size:
        assert time.monotonic() < deadline, f"{path} never reached {size} bytes"
        time.sleep(0.02)


def test_a_jail_that_never_reads_a_large_stdin_does_not_hold_destroy() -> None:
    """Eight megabytes of stdin, far past a pipe's capacity, for a command that only sleeps: the
    pump fills the pipe and waits; `destroy_jail` ends it and returns."""
    with tempfile.TemporaryDirectory(dir="/tmp") as streams:
        stdin = Path(streams) / "in"
        stdin.write_bytes(b"x" * (8 << 20))
        before = _open_fds()
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", "import time; time.sleep(60)"),
            stdio=Stdio(stdin=str(stdin)),
        )
        time.sleep(0.5)
        started = time.monotonic()
        destroy_jail(jail)
        took = time.monotonic() - started
        assert took < _BOUND_S, f"destroy_jail took {took:.1f}s"
        assert _open_fds() == before, "a pump left a host fd open"
        assert stdin.read_bytes() == b"x" * (8 << 20)


_FLOOD = "import os\nwhile True:\n    os.write(1, b'y' * 65536)\n"


def test_a_jail_flooding_stdout_into_a_file_does_not_hold_destroy() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as streams:
        stdout = Path(streams) / "out"
        before = _open_fds()
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _FLOOD), stdio=Stdio(stdout=str(stdout))
        )
        _wait_for_size(stdout, 1 << 20)  # the control: the flood reaches the file
        started = time.monotonic()
        destroy_jail(jail)
        took = time.monotonic() - started
        size = stdout.stat().st_size
        time.sleep(0.3)
        assert took < _BOUND_S, f"destroy_jail took {took:.1f}s"
        assert stdout.stat().st_size == size, "the file still grew after destroy_jail returned"
        assert _open_fds() == before, "a pump left a host fd open"


_STUCK_EMBEDDER = """
import json, sys, time
from brig import create_bwrap_jail, destroy_jail
jail = create_bwrap_jail((sys.executable, "-I", "-c", sys.argv[2]))
time.sleep(0.5)
started = time.monotonic()
destroy_jail(jail)
with open(sys.argv[1], "w") as report:
    json.dump({"took": time.monotonic() - started}, report)
"""
"""An embedder whose own stdout is a pipe nobody reads, running a flood with its own streams:
the pump cannot write on, and `destroy_jail` must still return. It reports how long that took
to a file, since its stdout is the stuck pipe."""


def test_a_jail_flooding_an_embedders_stuck_stdout_does_not_hold_destroy() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as scratch:
        report = Path(scratch) / "report.json"
        embedder = subprocess.Popen(
            (sys.executable, "-c", _STUCK_EMBEDDER, str(report), _FLOOD),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 30
            while not report.exists() or not report.read_text():
                assert embedder.poll() is None or report.exists(), "the embedder died"
                assert time.monotonic() < deadline, "destroy_jail never returned"
                time.sleep(0.05)
        finally:
            embedder.kill()
            embedder.communicate()
        took = json.loads(report.read_text())["took"]
    assert took < _BOUND_S, f"destroy_jail took {took:.1f}s"


def test_what_the_command_wrote_is_in_the_file_when_run_jail_returns() -> None:
    """Four megabytes on stdout and one on stderr, then exit: `run_jail` returns once the pumps
    have carried all of it, before `destroy_jail`."""
    program = (
        "import os\n"
        "for _ in range(64):\n"
        "    os.write(1, b'o' * 65536)\n"
        "os.write(2, b'e' * (1 << 20))\n"
    )
    with tempfile.TemporaryDirectory(dir="/tmp") as streams:
        stdout, stderr = Path(streams) / "out", Path(streams) / "err"
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", program),
            stdio=Stdio(stdout=str(stdout), stderr=str(stderr)),
        )
        try:
            assert run_jail(jail, timeout_s=15) == 0
            sizes = stdout.stat().st_size, stderr.stat().st_size
        finally:
            destroy_jail(jail)
    assert sizes == (64 * 65536, 1 << 20)
