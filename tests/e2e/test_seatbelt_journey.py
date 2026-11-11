"""TASK-0061: the Seatbelt jail's whole journey on a Mac, through brig's public API against the
real `/usr/bin/sandbox-exec`, nothing faked: create, run, interrupt, time out, destroy; the
command's working directory and environment; and teardown that leaves nothing of the jail
running. Darwin has no PID namespace to take a process that left the jail's group with it, so
teardown also kills every process that carries the jail's profile (`infra.members`); a process
that leaves the group, however, is still the jail's, and one outside the jail is never touched.
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


def test_a_jailed_command_may_start_a_session_of_its_own() -> None:
    """Leaving the group is allowed: a daemon's `setsid` works in a jail, as it does outside,
    and teardown finds what left by its sandbox instead."""
    program = (
        "import subprocess, sys\n"
        "child = subprocess.run([sys.executable, '-I', '-c', 'import os; os.setsid()'])\n"
        "sys.exit(child.returncode)\n"
    )
    jail = create_seatbelt_jail(_python(program))
    try:
        assert run_jail(jail, timeout_s=15) == 0
    finally:
        destroy_jail(jail)


def _escape(directory: Path, leave: str) -> str:
    """A command that spawns a shell out of its process group (`posix_spawn` with `leave`, as
    `setpgroup=0` or `setsid=True`), which waits, writes `after` into `directory` and sleeps on,
    prints its pid and exits at once, so the shell is launchd's child by the time teardown
    runs: the attack a group kill and a walk of the process tree both miss."""
    script = f"sleep 3; echo outlived > {directory}/after; sleep 60"
    return (
        "import os\n"
        f"pid = os.posix_spawn('/bin/sh', ['sh', '-c', {script!r}], os.environ, {leave})\n"
        "print(pid, flush=True)\n"
    )


@pytest.mark.parametrize("leave", ["setpgroup=0", "setsid=True"])
def test_a_process_that_left_the_group_does_not_outlive_destroy(tmp_path: Path, leave: str) -> None:
    directory = tmp_path / "d"
    directory.mkdir()
    out = tmp_path / "pid"
    jail = create_seatbelt_jail(
        _python(_escape(directory, leave)),
        policy=FsPolicy(readable=("/",), writable=(str(directory),)),
        stdio=Stdio(stdout=str(out)),
    )
    try:
        assert run_jail(jail, timeout_s=15) == 0
        escaped = int(out.read_text().strip())
        assert _alive(escaped), "control: the escaped shell runs on after the command exits"
        assert os.getpgid(escaped) != jail.process.pid, "control: it left the jail's group"
    finally:
        destroy_jail(jail)

    survived = _alive(escaped)
    time.sleep(4)
    wrote = (directory / "after").exists()
    if _alive(escaped):
        os.kill(escaped, signal.SIGKILL)
    assert not survived, "a process that left the jail's group outlived destroy_jail"
    assert not wrote


def test_destroy_kills_nothing_outside_the_jail() -> None:
    """The sweep finds a jail's processes by what its own profile decides, so another jail's
    and the host's own are left running."""
    host = subprocess.Popen(["/bin/sleep", "60"])
    other = create_seatbelt_jail(("/bin/sleep", "60"))
    try:
        jail = create_seatbelt_jail(("/bin/sleep", "60"))
        destroy_jail(jail)
        assert host.poll() is None, "a host process was killed"
        assert _alive(other.process.pid), "another jail's process was killed"
    finally:
        destroy_jail(other)
        host.kill()
        host.wait()


def test_destroy_leaves_no_process_of_the_jail_running(tmp_path: Path) -> None:
    """A command that starts a background process that takes itself out of the group, and
    exits: on Darwin the orphan is not the supervisor's to reap, and no group kill reaches it."""
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
