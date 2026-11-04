"""TASK-0050's repro: a candidate whose `status` has no `NSpid:` line is not the jail's PID 1.

`jail_pid1_namespace` scans the outer bwrap's children for the one whose `NSpid` ends in 1. A
task read mid-exit can open `status` and yield no `NSpid:` line (`_children` already concedes a
process can exit between the listing and the read). `_nspid`'s docstring says that reads as "this
candidate is not the jail's PID 1", never "the scan is over", so the scan skips it and keeps
looking until its deadline.

A gateway test of one `brig.infra` module (decision-0001 rule 4), against a procfs-shaped tree
this test plants in a throwaway directory, through `proc_root`, the module's own seam.
"""

import time
from pathlib import Path

from brig.infra import sockets

_BWRAP = 3000
_CANDIDATE = 3001


def _plant(proc_root: Path, pid: int, status: str) -> None:
    """A `<proc_root>/<pid>/status` holding `status`."""
    entry = proc_root / str(pid)
    entry.mkdir(parents=True)
    (entry / "status").write_text(status)


def test_a_child_without_an_nspid_line_is_skipped_until_the_deadline(tmp_path: Path) -> None:
    """bwrap is running and its one child's `status` carries `PPid:` but no `NSpid:`: no PID 1
    is found, so the scan answers `JailPid1NotFound` once its deadline passes."""
    proc_root = tmp_path / "proc"
    _plant(proc_root, _BWRAP, "Name:\tbwrap\nState:\tS (sleeping)\nPPid:\t1\nNSpid:\t3000\n")
    _plant(proc_root, _CANDIDATE, f"Name:\tgoing\nState:\tS (sleeping)\nPPid:\t{_BWRAP}\n")

    outcome = sockets.jail_pid1_namespace(_BWRAP, time.monotonic() + 0.2, str(proc_root))

    assert outcome == sockets.JailPid1NotFound()
