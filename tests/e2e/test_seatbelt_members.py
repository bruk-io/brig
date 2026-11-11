"""TASK-0061 and decision-0010 item 2: `infra.members` against this Mac's real `sandbox_check`,
the call a Seatbelt jail's teardown finds the jail's processes with. What it answers is pinned
here, because the sweep's correctness rests on it: a process that is gone reads as refused (so
a scan must notice a process that vanished under it), and the jail's own running supervisor is
found carrying its profile (the canary)."""

import os
import subprocess
import sys
import time
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


def _broadly_sandboxed(tmp_path: Path) -> subprocess.Popen[bytes]:
    """A process under a sandbox that allows everything but one file, `tmp_path/denied`, as a
    tool's own sandbox may: it may read any mark. The one denied file shows when its profile
    has applied. In a session of its own, so a regression that kills its group spares this
    test's."""
    denied = tmp_path / "denied"
    denied.write_text("")
    profile = f'(version 1)(allow default)(deny file-read-metadata (literal "{denied}"))'
    bystander = subprocess.Popen(
        ["/usr/bin/sandbox-exec", "-p", profile, "/bin/sleep", "30"], start_new_session=True
    )
    deadline = time.monotonic() + 5
    while members.profile_decision(bystander.pid, str(denied)) != 1:
        assert time.monotonic() < deadline, "the sandboxed process never came up"
        time.sleep(0.02)
    return bystander


def test_with_its_decoy_gone_a_mark_makes_no_broadly_sandboxed_process_a_member(
    tmp_path: Path,
) -> None:
    """The reviewer's repro: `sandbox_check` reads a missing path as refused, so with the decoy
    gone a process that may read the mark would pass as the jail's and be killed."""
    mark = tmp_path / "x.mark"
    mark.write_text("")
    missing = tmp_path / "x.decoy"
    bystander = _broadly_sandboxed(tmp_path)
    try:
        assert members.profile_decision(bystander.pid, str(mark)) == 0, (
            "control: the bystander may read the mark"
        )
        assert members.profile_decision(bystander.pid, str(missing)) == 1, (
            "control: the missing decoy reads as refused"
        )
        member = members.is_member(str(mark), str(missing), bystander.pid)
        swept = members.freeze_and_kill(str(mark), str(missing), time.monotonic() + 1)
        alive = bystander.poll() is None
    finally:
        bystander.kill()
        bystander.wait()

    assert not member
    assert not swept, "nothing can be told apart without the decoy, so nothing is swept"
    assert alive, "a broadly sandboxed bystander was killed"


def test_a_kept_mark_whose_decoy_is_gone_is_never_swept(tmp_path: Path) -> None:
    mark = tmp_path / "brig-supervisor-x.mark"
    mark.write_text("")
    bystander = _broadly_sandboxed(tmp_path)
    try:
        members.reap_kept(str(tmp_path), time.monotonic() + 1)
        alive = bystander.poll() is None
    finally:
        bystander.kill()
        bystander.wait()

    assert alive, "a broadly sandboxed bystander was killed by the kept-mark sweep"
    assert mark.exists(), "the mark is left where it is, not removed"
