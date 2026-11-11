"""TASK-0061 and decision-0010 item 2: `infra.members` against this Mac's real `sandbox_check`,
the call a Seatbelt jail's teardown finds the jail's processes with. What it answers is pinned
here, because the sweep's correctness rests on it: a process that is gone reads as refused (so
a scan must notice a process that vanished under it), and the jail's own running supervisor is
found carrying its profile (the canary)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from brig import create_seatbelt_jail, destroy_jail
from brig.infra import members

pytestmark = pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").exists(),
    reason="sandbox-exec is Darwin's; test skips on Linux, runs on a Mac",
)


def test_a_process_that_is_gone_reads_as_refused(tmp_path: Path) -> None:
    exists = tmp_path / "exists"
    exists.write_text("")
    gone = subprocess.Popen(["/usr/bin/true"])
    gone.wait()

    assert members.profile_decision(gone.pid, str(exists)) == 1


def test_an_unsandboxed_process_reads_as_allowed(tmp_path: Path) -> None:
    exists = tmp_path / "exists"
    exists.write_text("")

    assert members.profile_decision(os.getppid(), str(exists)) == 0


def test_a_running_jail_s_supervisor_is_found_carrying_its_profile() -> None:
    jail = create_seatbelt_jail((sys.executable, "-I", "-c", "import time; time.sleep(30)"))
    try:
        assert jail.member_mark is not None
        decoy = jail.member_mark.with_suffix(".decoy")
        assert members.is_member(str(jail.member_mark), str(decoy), jail.process.pid)
        assert not members.is_member(str(jail.member_mark), str(decoy), os.getpid())
    finally:
        destroy_jail(jail)
