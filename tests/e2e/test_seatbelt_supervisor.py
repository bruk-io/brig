"""TASK-0061, law 6 and decision-0010 item 2: on a Mac, what the host believes about a Seatbelt
jail comes from its supervisor, which the command cannot speak for. The command holds none of
the supervisor's wire, and a `ptrace` of its supervisor kills it (`PT_DENY_ATTACH`), so the exit
code the host reads is the one `waitpid(2)` gave.

What differs from Linux, where the supervisor is PID 1 of the jail's own namespace: on Darwin
the supervisor shares the command's sandbox, so the command can signal it, and a command that
kills its supervisor loses its own exit code. The host is then told the code is unknown, never
a code the command chose.
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from brig import JailExitUnknown, create_seatbelt_jail, destroy_jail, run_jail
from brig.infra.supervisor import program

pytestmark = pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").exists(),
    reason="sandbox-exec is Darwin's; test skips on Linux, runs on a Mac",
)


def _exit_of(program: str) -> int:
    jail = create_seatbelt_jail((sys.executable, "-I", "-c", program))
    try:
        return run_jail(jail, timeout_s=15)
    finally:
        destroy_jail(jail)


def test_the_command_holds_none_of_the_supervisor_s_wire() -> None:
    program = (
        "import os, sys\n"
        "for fd in (3, 4, 5):\n"
        "    try:\n"
        "        os.fstat(fd)\n"
        "    except OSError:\n"
        "        continue\n"
        "    sys.exit(fd)\n"
    )

    assert _exit_of(program) == 0


def test_a_command_that_ptraces_its_supervisor_is_killed_for_it() -> None:
    program = (
        "import ctypes, os, sys\n"
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        "libc.ptrace.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]\n"
        "libc.ptrace(14, os.getppid(), None, 0)\n"
        "sys.exit(5)\n"
    )

    assert _exit_of(program) == -11, "PT_DENY_ATTACH answers an attach with SIGSEGV"


def test_a_command_that_kills_its_supervisor_leaves_its_exit_code_unknown() -> None:
    program = "import os, signal, time\nos.kill(os.getppid(), signal.SIGKILL)\ntime.sleep(5)\n"
    jail = create_seatbelt_jail((sys.executable, "-I", "-c", program))
    try:
        with pytest.raises(JailExitUnknown):
            run_jail(jail, timeout_s=15)
    finally:
        destroy_jail(jail)


def _freezers() -> set[int]:
    """Every process on the host that carries the teardown freezer's argument."""
    found = subprocess.run(
        ["/usr/bin/pgrep", "-f", "brig-teardown-freezer"], capture_output=True, text=True
    )
    return {int(pid) for pid in found.stdout.split()}


def _settle(before: set[int], expected: int) -> set[int]:
    deadline = time.monotonic() + 5
    while True:
        now = _freezers() - before
        if len(now) == expected or time.monotonic() >= deadline:
            return now
        time.sleep(0.05)


def test_a_jail_has_one_freezer_and_destroy_ends_it() -> None:
    before = _freezers()
    jail = create_seatbelt_jail(("/bin/sleep", "30"))
    try:
        during = _settle(before, 1)
    finally:
        destroy_jail(jail)
    after = _settle(before, 0)

    assert len(during) == 1
    assert after == set()


def test_a_supervisor_outside_a_sandbox_starts_no_freezer_even_when_asked() -> None:
    """Outside a sandbox the freezer's `kill(-1, SIGSTOP)` would stop every process of the
    user: run unjailed with the freezer's argument (no wire fds, so it ends at once), the
    supervisor's freezer must see it is not sandboxed and exit."""
    before = _freezers()
    supervisor = subprocess.run(
        [sys.executable, "-I", program.__file__, program.FREEZER_FLAG],
        capture_output=True,
        timeout=30,
        check=False,
    )
    left = _settle(before, 0)
    for pid in left:
        subprocess.run(["/bin/kill", "-9", str(pid)], check=False)

    assert supervisor.returncode != 0, "control: with no wire fds the supervisor fails"
    assert left == set(), "an unsandboxed freezer was left running"
