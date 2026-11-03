"""TASK-0001.31: no directory on the way from a writable root to a write deny or a mask can be
renamed from inside the jail, through the public API against real bwrap.

A deny or a mask is a mount on the entry it names, and a mount moves with its parent: renaming
`W/a` takes the deny at `W/a/b/f` with it, and the command could then make its own `W/a/b/f`,
which the host reads once the jail is gone. So each directory strictly between the writable root
and the protected path is a mount point of its own (old SPEC decision-168: renaming a mount point
inside the mount namespace fails with `EBUSY`). The probe tries to rename each such directory and
one beside them that is on the way to nothing (the positive control: renames work in the root),
and reports what happened; the host then reads the protected paths.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from brig import (
    FS_WRITE_CLAIM,
    Evidence,
    FsPolicy,
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

_RENAME_PROBE = """
import errno, json, os, sys
report, control, *pinned = sys.argv[1:]

def renamed(path):
    try:
        os.rename(path, path + "-moved")
    except OSError as error:
        return errno.errorcode.get(error.errno, str(error.errno))
    os.rename(path + "-moved", path)  # back, so the next one is tried where it was
    return "renamed"

found = {"control": renamed(control), "pinned": {path: renamed(path) for path in pinned}}
with open(report, "w") as handle:
    json.dump(found, handle)
"""
"""Rename the control directory and each pinned one to `<path>-moved` (and back, when it moved);
write what each did (`"renamed"` or the errno's name) to `report` as JSON."""


def _renames(
    jail_root: Path, policy: FsPolicy, pinned: tuple[Path, ...]
) -> tuple[dict[str, Any], Jail]:
    """Run the probe in a jail under `policy` against `pinned`, with `jail_root/free` as the
    control, and return its report and the jail."""
    control = jail_root / "free"
    control.mkdir()
    report = jail_root / "report.json"
    jail = create_bwrap_jail(
        (sys.executable, "-I", "-c", _RENAME_PROBE, str(report), str(control), *map(str, pinned)),
        policy=policy,
    )
    try:
        assert run_jail(jail, timeout_s=15) == 0
    finally:
        destroy_jail(jail)
    return json.loads(report.read_text()), jail


def _held(jail: Jail, found: dict[str, Any]) -> None:
    """No directory on the way was renamed, and the report is no stronger than that measures."""
    control = found["control"] == "renamed"
    moved = [path for path, outcome in found["pinned"].items() if outcome == "renamed"]
    measured = grade(
        (FS_WRITE_CLAIM,),
        {FS_WRITE_CLAIM: Evidence(control_observed=control, violation_blocked=not moved)},
    )
    assert control, f"the control rename failed, so the probe proves nothing: {found}"
    assert not moved, f"the jail renamed a directory on the way to a protected path: {found}"
    assert at_most(jail.report[FS_WRITE_CLAIM], measured[FS_WRITE_CLAIM])


def test_no_directory_on_the_way_to_a_deny_can_be_renamed() -> None:
    """A deny on a file two directories into the writable root: neither directory moves, and the
    host's file is still the one it wrote."""
    with tempfile.TemporaryDirectory(dir="/tmp") as top:
        root = Path(top)
        config = root / "a" / "b" / "config"
        config.parent.mkdir(parents=True)
        config.write_text("the person's")
        policy = FsPolicy(readable=("/",), writable=(top,), write_denies=(str(config),))

        found, jail = _renames(root, policy, (root / "a", root / "a" / "b"))

        _held(jail, found)
        assert config.read_text() == "the person's"


def test_no_directory_on_the_way_to_a_mask_can_be_renamed() -> None:
    """A mask on a directory of keys under two directories of the writable root."""
    with tempfile.TemporaryDirectory(dir="/tmp") as top:
        root = Path(top)
        keys = root / "home" / "me" / "keys"
        keys.mkdir(parents=True)
        (keys / "id").write_text("secret")
        policy = FsPolicy(readable=("/",), writable=(top,), masks=(str(keys),))

        found, jail = _renames(root, policy, (root / "home", root / "home" / "me"))

        _held(jail, found)
        assert (keys / "id").read_text() == "secret"


def test_no_directory_on_the_way_to_an_absent_deny_can_be_renamed() -> None:
    """An absent deny at `.git/hooks` under a `.git` that exists, and one at `cfg/deep/rc` where
    neither directory exists yet: brig makes those before the jail starts, so they are pinned
    too."""
    with tempfile.TemporaryDirectory(dir="/tmp") as top:
        root = Path(top)
        (root / ".git").mkdir()
        policy = FsPolicy(
            readable=("/",),
            writable=(top,),
            write_denies=(f"{top}/.git/hooks", f"{top}/cfg/deep/rc"),
        )

        found, jail = _renames(root, policy, (root / ".git", root / "cfg", root / "cfg" / "deep"))

        _held(jail, found)


def test_no_directory_on_the_way_to_a_nested_readable_root_nor_the_root_can_be_renamed() -> None:
    """TASK-0001.33: a readable root two directories into the writable root (an embedder's own
    code, kept read-only inside a project). Neither directory on the way, nor the readable root
    itself, moves, and the host's file there is still the one it wrote."""
    with tempfile.TemporaryDirectory(dir="/tmp") as top:
        root = Path(top)
        tool = root / "z" / "y" / "r" / "tool"
        tool.parent.mkdir(parents=True)
        tool.write_text("the host's")
        policy = FsPolicy(readable=("/", str(tool.parent)), writable=(top,))

        found, jail = _renames(root, policy, (root / "z", root / "z" / "y", root / "z" / "y" / "r"))

        _held(jail, found)
        assert tool.read_text() == "the host's"
