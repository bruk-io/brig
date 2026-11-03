"""TASK-0027: the directories bwrap needs at absent write denies and masks under a writable root
are brig's to make and to remove, and none outlives the last jail over them, through the public
API against real bwrap.

Two jails over one tree, each holding an absent `.envrc` (a deny), an absent `.git/hooks` (a
deny under a `.git` that already exists) and an absent `secret.env` (a mask). The first jail's
teardown leaves the second's holds in place, and the second still cannot create any of them; the
second's teardown leaves the tree exactly as it was, `.git` included.
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

from brig import FsPolicy, create_bwrap_jail, destroy_jail

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_PROBE = """
import os, sys, time
root, go, report = sys.argv[1:4]
while not os.path.exists(go):
    time.sleep(0.02)
made = []
for name in (".envrc", ".git/hooks/pre-commit", "secret.env"):
    try:
        with open(os.path.join(root, name), "w") as handle:
            handle.write("planted")
        made.append(name)
    except OSError:
        pass
with open(report, "w") as handle:
    handle.write(",".join(made) or "none")
time.sleep(600)
"""
"""Wait for `go`, try to create each held path, report which it could, then stay up."""


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


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


def test_placeholders_outlive_no_jail_and_none_is_removed_under_another() -> None:
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as top,
        tempfile.TemporaryDirectory(dir="/tmp") as side,
    ):
        root = Path(top)
        (root / ".git").mkdir()
        (root / "kept.txt").write_text("the person's")
        before = _tree(root)
        policy = FsPolicy(
            readable=("/",),
            writable=(top, side),  # side: where the probe's go and report files are
            write_denies=(f"{top}/.envrc", f"{top}/.git/hooks"),
            masks=(f"{top}/secret.env",),
        )
        go, report = Path(side) / "go", Path(side) / "report"
        first = create_bwrap_jail(
            (sys.executable, "-c", "import time; time.sleep(600)"), policy=policy
        )
        second = create_bwrap_jail(
            (sys.executable, "-c", _PROBE, top, str(go), str(report)), policy=policy
        )
        try:
            destroy_jail(first)
            assert (root / ".envrc").is_dir() and (root / ".git" / "hooks").is_dir()
            go.write_text("")
            _wait_for(report)
            assert report.read_text() == "none", "the second jail created a held path"
        finally:
            destroy_jail(second)
        assert _tree(root) == before
        assert (root / "kept.txt").read_text() == "the person's"
        assert not any(os.scandir(root / ".git"))
