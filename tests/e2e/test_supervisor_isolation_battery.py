"""TASK-0022, decision-0006: the supervised command cannot write the supervisor's wire.

The command is the supervisor's direct child, under the same uid, with its own procfs. Before
decision-0006 it reopened the supervisor's events pipe through `/proc/1/fd/<n>` and wrote a
`done` of its own, which `run_jail` trusted. This plants that attempt through the public API
and asserts `run_jail` reports the command's real exit code, after the command really ran.

The positive control is the same reopen aimed at a pipe a child of the command's own holds:
it succeeds there, so a refusal at PID 1 is the supervisor's protection, not procfs being
unavailable in the jail. A second test asserts the command holds no capability, whoever runs
brig (decision-0006 item 2).

Each probe reports through the command's exit code, since a command's stdout is the embedder's
own (DRAFT-0016) and an exit code is what `run_jail` hands back anyway.
"""

import shutil
import sys
import time

import pytest

from brig import create_bwrap_jail, destroy_jail, run_jail

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_REAL_EXIT_CODE = 7
"""What the forging command exits with after its attempt: the code `run_jail` must report."""

_FORGED_EXIT_CODE = 42
"""What the forging command writes into the supervisor's events pipe as its `done`."""

_FORGER = f"""
import os, time
try:
    held = os.listdir("/proc/1/fd")
    targets = [n for n in held if os.readlink(f"/proc/1/fd/{{n}}").startswith("pipe:")]
except OSError:
    targets = []
for n in targets:
    try:
        fd = os.open(f"/proc/1/fd/{{n}}", os.O_WRONLY)
        os.write(fd, b'{{"kind": "done", "exit_code": {_FORGED_EXIT_CODE}}}\\n')
        os.close(fd)
    except OSError:
        pass
time.sleep(1)
raise SystemExit({_REAL_EXIT_CODE})
"""
"""Write a forged `done` into every pipe the supervisor holds, then run on and exit with the
real code. Before decision-0006 `run_jail` returned the forged code within milliseconds."""

_CONTROL = """
import os, sys, time
read_end, write_end = os.pipe()
child = os.fork()
if child == 0:
    os.close(read_end)
    time.sleep(5)
    os._exit(0)
os.close(write_end)
time.sleep(0.2)
reached = 0
for n in os.listdir(f"/proc/{child}/fd"):
    if os.readlink(f"/proc/{child}/fd/{n}").startswith("pipe:"):
        try:
            os.close(os.open(f"/proc/{child}/fd/{n}", os.O_WRONLY))
            reached = 1
        except OSError:
            pass
os.kill(child, 9)
os.waitpid(child, 0)
raise SystemExit(10 + reached)
"""
"""Reopen, through procfs, a pipe the command's own forked child holds: exits 11 when that
works, 10 when it does not."""

_CAPABILITIES = """
status = dict(line.split(":", 1) for line in open("/proc/self/status"))
raise SystemExit(0 if int(status["CapEff"].strip(), 16) == 0 else 1)
"""
"""Exit 0 when the command holds no effective capability, 1 otherwise."""


def _exit_code_of(program: str) -> tuple[int, float]:
    """Run `program` as a jail's command under the default policy: its exit code as
    `run_jail` reports it, and how long that took."""
    jail = create_bwrap_jail((sys.executable, "-I", "-c", program))
    started = time.monotonic()
    try:
        return run_jail(jail, timeout_s=20), time.monotonic() - started
    finally:
        destroy_jail(jail)


def test_a_command_cannot_forge_the_supervisors_done() -> None:
    """The command writes a forged `done` into every pipe of PID 1's it can reopen, then runs
    on for a second and exits with its real code: `run_jail` reports the real code, after the
    second, and never the forged one."""
    exit_code, elapsed = _exit_code_of(_FORGER)
    assert exit_code == _REAL_EXIT_CODE, f"run_jail trusted a forged done ({exit_code})"
    assert elapsed >= 0.9, f"run_jail returned after {elapsed:.2f}s, before the command ended"


def test_the_same_reopen_reaches_a_pipe_of_the_commands_own_child() -> None:
    """Positive control: procfs reopening works in the jail, aimed at a process the command
    owns, so the refusal at PID 1 above is the supervisor's doing."""
    exit_code, _ = _exit_code_of(_CONTROL)
    assert exit_code == 11, exit_code


def test_the_command_holds_no_capability() -> None:
    """decision-0006 item 2: `--cap-drop ALL`, so even a jail brig's root caller starts holds
    no capability inside its namespaces."""
    exit_code, _ = _exit_code_of(_CAPABILITIES)
    assert exit_code == 0, "the jailed command holds capabilities"
