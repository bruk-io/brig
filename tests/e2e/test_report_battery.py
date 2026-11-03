"""decision-0008: no claim a jail's report states is stronger than what this battery measures.

Each claim's violation is planted against a real jail with a positive control beside it, graded
with `grade` from the evidence, and the jail's own report is held to that (`at_most`). A
regression in a mechanism grades the claim lower here and fails the report's ceiling.
"""

import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

import pytest

from brig import (
    ENV_CLAIM,
    FS_READ_CLAIM,
    FS_WRITE_CLAIM,
    NETWORK_CLAIM,
    WHOLE_HOST_READ_ONLY,
    Claim,
    EnvPolicy,
    Evidence,
    FsPolicy,
    Grade,
    Jail,
    at_most,
    create_bwrap_jail,
    destroy_jail,
    grade,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)


def _exit(program: str, *argv: str, **kwargs: object) -> tuple[int, Jail]:
    jail = create_bwrap_jail((sys.executable, "-I", "-c", program, *argv), **kwargs)  # type: ignore[arg-type]
    try:
        return run_jail(jail, timeout_s=15), jail
    finally:
        destroy_jail(jail)


def _held_to(jail: Jail, claim: Claim, control: bool, blocked: bool) -> None:
    measured = grade(
        (claim,), {claim: Evidence(control_observed=control, violation_blocked=blocked)}
    )
    assert at_most(jail.report[claim], measured[claim]), (claim.name, jail.report[claim], measured)


def test_network_no_connection_leaves_the_jail() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            control = True  # the host itself reaches it
        program = (
            "import socket, sys\n"
            "try:\n"
            "    socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=3)\n"
            "except OSError:\n"
            "    sys.exit(7)\n"
        )
        code, jail = _exit(program, str(port))
    _held_to(jail, NETWORK_CLAIM, control, blocked=code == 7)


def test_fs_write_a_write_outside_the_writable_root_is_refused() -> None:
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as root,
        tempfile.TemporaryDirectory(dir="/tmp") as outside,
    ):
        program = (
            "import sys\n"
            "open(sys.argv[1] + '/inside', 'w').write('x')\n"
            "try:\n"
            "    open(sys.argv[2] + '/outside', 'w').write('x')\n"
            "except OSError:\n"
            "    sys.exit(7)\n"
        )
        code, jail = _exit(
            program, root, outside, policy=FsPolicy(readable=("/",), writable=(root,))
        )
        control = (Path(root) / "inside").exists()
        blocked = code == 7 and not (Path(outside) / "outside").exists()
    _held_to(jail, FS_WRITE_CLAIM, control, blocked)


def test_fs_read_a_masked_file_reads_nothing_of_the_host() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as root:
        secret, plain = Path(root) / "secret", Path(root) / "plain"
        secret.write_text("hunter2")
        plain.write_text("visible")
        program = (
            "import sys\n"
            "assert open(sys.argv[2]).read() == 'visible'\n"
            "try:\n"
            "    leaked = 'hunter2' in open(sys.argv[1]).read()\n"
            "except OSError:\n"
            "    leaked = False\n"
            "sys.exit(9 if leaked else 7)\n"
        )
        code, jail = _exit(
            program, str(secret), str(plain), policy=FsPolicy(readable=("/",), masks=(str(secret),))
        )
    _held_to(jail, FS_READ_CLAIM, control=code in (7, 9), blocked=code == 7)


def test_env_only_the_allowed_variables_reach_the_command() -> None:
    os.environ["BRIG_REPORT_ALLOWED"] = "yes"
    os.environ["BRIG_REPORT_SECRET"] = "no"
    try:
        program = (
            "import os, sys\n"
            "control = os.environ.get('BRIG_REPORT_ALLOWED') == 'yes'\n"
            "leaked = 'BRIG_REPORT_SECRET' in os.environ\n"
            "sys.exit((1 if control else 0) + (2 if leaked else 0))\n"
        )
        code, jail = _exit(
            program,
            env=tuple(os.environ.items()),
            env_policy=EnvPolicy(allowed=("BRIG_REPORT_ALLOWED",)),
        )
    finally:
        del os.environ["BRIG_REPORT_ALLOWED"], os.environ["BRIG_REPORT_SECRET"]
    _held_to(jail, ENV_CLAIM, control=bool(code & 1), blocked=not code & 2)


def test_a_mask_inside_a_writable_root_is_reported_best_effort() -> None:
    """What the report says when the host could undo a mask: no stronger than best-effort."""
    with tempfile.TemporaryDirectory(dir="/tmp") as root:
        (Path(root) / "secret").write_text("x")
        _, jail = _exit(
            "pass", policy=FsPolicy(readable=("/",), writable=(root,), masks=(f"{root}/secret",))
        )
    assert jail.report[FS_READ_CLAIM] is Grade.BEST_EFFORT
    _, default = _exit("pass", policy=WHOLE_HOST_READ_ONLY)
    assert default.report[FS_READ_CLAIM] is Grade.ENFORCED
