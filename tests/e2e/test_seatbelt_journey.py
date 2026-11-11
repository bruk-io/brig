"""TASK-0061: the Seatbelt jail's whole journey on a Mac, through brig's public API against the
real `/usr/bin/sandbox-exec`, nothing faked: create, run, interrupt, time out, destroy; the
command's working directory and environment; and teardown that leaves nothing of the jail
running, which on Darwin rests on the profile refusing `setsid` and `setpgid` (no PID namespace
takes a process that left the group with it).
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from brig import (
    SEATBELT_ENV_CLAIM,
    EnvPolicy,
    Evidence,
    FsPolicy,
    JailWaitTimedOut,
    Stdio,
    at_most,
    create_seatbelt_jail,
    destroy_jail,
    grade,
    interrupt_jail,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").exists(),
    reason="sandbox-exec is Darwin's; test skips on Linux, runs on a Mac",
)

_REFUSED = 7
"""What a probe exits with when the kernel refused it (`EPERM` or `EACCES`)."""


def _python(program: str, *argv: str) -> tuple[str, ...]:
    return (sys.executable, "-I", "-c", program, *argv)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_a_command_runs_and_its_exit_code_comes_back() -> None:
    jail = create_seatbelt_jail(("/bin/sh", "-c", "exit 3"))
    try:
        assert run_jail(jail, timeout_s=15) == 3
    finally:
        destroy_jail(jail)


def test_a_command_that_never_exits_times_out() -> None:
    jail = create_seatbelt_jail(("/bin/sleep", "9999"))
    try:
        with pytest.raises(JailWaitTimedOut):
            run_jail(jail, timeout_s=0.5)
    finally:
        destroy_jail(jail)


def test_an_interrupt_reaches_the_command() -> None:
    program = (
        "import signal, sys, time\n"
        "signal.signal(signal.SIGINT, lambda *_: sys.exit(42))\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
        "sys.exit(1)\n"
    )
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(os.path.realpath(scratch)) / "out"
        jail = create_seatbelt_jail(_python(program), stdio=Stdio(stdout=str(out)))
        try:
            deadline = time.monotonic() + 10
            while b"ready" not in (out.read_bytes() if out.exists() else b""):
                assert time.monotonic() < deadline, "the command never started"
                time.sleep(0.05)
            assert interrupt_jail(jail) is True
            assert run_jail(jail, timeout_s=15) == 42
        finally:
            destroy_jail(jail)


def test_the_command_runs_in_the_cwd_it_is_given(tmp_path: Path) -> None:
    out = tmp_path / "out"
    work = tmp_path / "work"
    work.mkdir()
    jail = create_seatbelt_jail(
        _python("import os; print(os.getcwd())"),
        cwd=str(work),
        stdio=Stdio(stdout=str(out)),
    )
    try:
        assert run_jail(jail, timeout_s=15) == 0
    finally:
        destroy_jail(jail)

    assert out.read_text().strip() == str(work)


def test_the_command_sees_only_the_environment_its_policy_allows(tmp_path: Path) -> None:
    out = tmp_path / "out"
    program = "import os; print(sorted(k for k in os.environ if k.startswith('BRIG_PROBE_')))"
    jail = create_seatbelt_jail(
        _python(program),
        env={"BRIG_PROBE_ALLOWED": "1", "BRIG_PROBE_SECRET": "hunter2"},
        env_policy=EnvPolicy(allowed=("BRIG_PROBE_ALLOWED",)),
        stdio=Stdio(stdout=str(out)),
    )
    try:
        assert run_jail(jail, timeout_s=15) == 0
    finally:
        destroy_jail(jail)

    seen = out.read_text().strip()
    control = "BRIG_PROBE_ALLOWED" in seen
    blocked = "BRIG_PROBE_SECRET" not in seen
    measured = grade(
        (SEATBELT_ENV_CLAIM,),
        {SEATBELT_ENV_CLAIM: Evidence(control_observed=control, violation_blocked=blocked)},
    )
    assert (control, blocked) == (True, True), seen
    assert at_most(jail.report[SEATBELT_ENV_CLAIM], measured[SEATBELT_ENV_CLAIM])


_LEAVE_GROUP = (
    "import os, sys\n"
    "for leave in (os.setsid, lambda: os.setpgid(0, 0)):\n"
    "    try:\n"
    "        leave()\n"
    "    except PermissionError:\n"
    "        continue\n"
    "    sys.exit(0)\n"
    f"sys.exit({_REFUSED})\n"
)
"""Try to leave the process group: `setsid`, then `setpgid`. Exits 0 if either worked, 7 if
both were refused. Run as a child, never as a group leader, so `setsid` can succeed."""


def test_the_command_cannot_leave_the_jail_s_process_group() -> None:
    wrapper = (
        "import subprocess, sys\n"
        "sys.exit(subprocess.run([sys.executable, '-I', '-c', sys.argv[1]]).returncode)\n"
    )
    control = subprocess.run(_python(wrapper, _LEAVE_GROUP), check=False).returncode
    jail = create_seatbelt_jail(_python(wrapper, _LEAVE_GROUP))
    try:
        jailed = run_jail(jail, timeout_s=15)
    finally:
        destroy_jail(jail)

    assert control == 0, "control: an unjailed child leaves its group"
    assert jailed == _REFUSED


def test_destroy_leaves_no_process_of_the_jail_running(tmp_path: Path) -> None:
    """A command that starts a background process, tries to take it out of the group, and
    exits: on Darwin the orphan is not the supervisor's to reap, so only the group kill ends
    it."""
    pid_file = tmp_path / "pid"
    program = (
        "import os, subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-I', '-c', "
        "'import os, time\\ntry:\\n    os.setsid()\\nexcept OSError:\\n    pass\\n"
        "time.sleep(120)'])\n"
        "print(child.pid, flush=True)\n"
    )
    jail = create_seatbelt_jail(_python(program), stdio=Stdio(stdout=str(pid_file)))
    try:
        assert run_jail(jail, timeout_s=15) == 0
        orphan = int(pid_file.read_text().strip())
        assert _alive(orphan), "the background process should outlive the command"
    finally:
        destroy_jail(jail)

    deadline = time.monotonic() + 5
    while _alive(orphan) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _alive(orphan):
        os.kill(orphan, signal.SIGKILL)
        pytest.fail("a process of the jail outlived destroy_jail")


def test_a_policy_s_writable_root_is_where_the_command_writes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    jail = create_seatbelt_jail(
        ("/bin/sh", "-c", f"echo made > {project}/made"),
        policy=FsPolicy(readable=("/",), writable=(str(project),)),
    )
    try:
        assert run_jail(jail, timeout_s=15) == 0
    finally:
        destroy_jail(jail)

    assert (project / "made").read_text() == "made\n"
