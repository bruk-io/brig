"""TASK-0020: an embedder can interrupt a running jail's command, through the public API.

The command installs a `SIGINT` handler, says it is ready by writing a file in its writable
directory, and exits 0 only if the interrupt arrived and it kept running afterwards; 1 if it
waited 10 s and none came. A finished jail answers `False`, never a raise.
"""

import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

from brig import FsPolicy, create_bwrap_jail, destroy_jail, interrupt_jail, run_jail

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_INTERRUPTIBLE = """
import signal, sys, time
from pathlib import Path
interrupted = []
signal.signal(signal.SIGINT, lambda sig, frame: interrupted.append(sig))
Path(sys.argv[1]).write_text("ready")
deadline = time.monotonic() + 10
while not interrupted and time.monotonic() < deadline:
    time.sleep(0.02)
time.sleep(0.2)  # still running after the interrupt
sys.exit(0 if interrupted else 1)
"""


def _wait_for(path: Path, timeout_s: float = 10.0) -> None:
    """Poll until `path` exists.

    Raises:
        TimeoutError: it never appeared.
    """
    deadline = time.monotonic() + timeout_s
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{path} never appeared")
        time.sleep(0.02)


def test_interrupting_a_running_jail_reaches_its_command_which_keeps_running() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as root:
        ready = Path(root) / "ready"
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _INTERRUPTIBLE, str(ready)),
            policy=FsPolicy(readable=("/",), writable=(root,)),
        )
        try:
            _wait_for(ready)
            assert interrupt_jail(jail) is True
            assert run_jail(jail, timeout_s=15) == 0
        finally:
            destroy_jail(jail)


def test_interrupting_a_finished_jail_answers_false() -> None:
    jail = create_bwrap_jail((sys.executable, "-I", "-c", "pass"))
    try:
        assert run_jail(jail, timeout_s=15) == 0
        assert interrupt_jail(jail) is False
    finally:
        destroy_jail(jail)


def test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost() -> None:
    """The supervisor holds SIGINT back from the moment it starts until it can forward it, so
    an interrupt sent right after `create_bwrap_jail` returns still reaches the command: it dies
    of it instead of sleeping on and exiting 0. Twenty times, since the lost case is a window."""
    for _ in range(20):
        jail = create_bwrap_jail((sys.executable, "-I", "-c", "import time; time.sleep(3)"))
        try:
            delivered = interrupt_jail(jail)
            exit_code = run_jail(jail, timeout_s=15)
        finally:
            destroy_jail(jail)
        assert not (delivered and exit_code == 0), "interrupt_jail said True and nothing arrived"
        assert delivered, "the jail's command was running, yet nothing was signalled"
