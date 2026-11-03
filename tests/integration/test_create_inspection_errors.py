"""TASK-0047's repro: before a jail starts, `create_bwrap_jail` inspects the paths its policy and
stdio name, and reads brig's own supervisor source, and each can fail with the host's `OSError`.

1. A policy path beneath a directory the embedder's user cannot search: `files.facts`'s `stat`
   raises `PermissionError`, which crosses the API bare.
2. A policy path that is a symbolic link loop: the same `stat` raises `ELOOP`, bare.
3. A stdio path through a link the embedder's user cannot read (another user's
   `/proc/<pid>/cwd`: `lstat` says it is a link, `readlink` is refused): `files.link_chain`'s
   `readlink` raises `PermissionError`, bare.
4. An install whose supervisor source is gone: reading it raises inside the script write's error
   handling, so a broken install reads as `StateDirectoryWriteFailed`, a full or unwritable state
   directory.

Each failure is made real in a child Python with its own `BRIG_HOME` (the parent's state
directory is resolved once per process). We run as root, who searches every directory and reads
every link, so the first and third children import everything they need and then drop to the
`nobody` user (65534) before they create the jail. The fourth imports brig from a copy of its
source and deletes the copy's supervisor program once imported. The world past the policy's
inspection is faked at infra's edge (decision-0001 rule 5); each test catches whatever crosses and
asserts on it, so each fails on what it pins, not on an error it did not expect.
"""

import errno
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

import brig

_NOBODY = 65534
"""The user the first and third children drop to: not root, so the host's permissions hold."""

_ROOT = Path(__file__).resolve().parents[2]

_CHILD = """
import json, os, sys
mode, work = sys.argv[1], sys.argv[2]
if mode == "source":
    sys.path.insert(0, f"{work}/site")
from tests.integration.fakes import FakeChannelDirectories, FakePlaceholders, FakeProcesses
import brig

kwargs = {}
if mode == "denied":
    kwargs["policy"] = brig.FsPolicy(readable=("/", f"{work}/locked/inside"))
elif mode == "loop":
    kwargs["policy"] = brig.FsPolicy(readable=("/", f"{work}/loop"))
elif mode == "readlink":
    kwargs["stdio"] = brig.Stdio(stdout=f"/proc/{os.getppid()}/cwd/out.txt")
elif mode == "source":
    package = os.path.dirname(brig.__file__)
    assert package == f"{work}/site/brig", package
    os.unlink(os.path.join(package, "infra", "supervisor", "program.py"))
if mode in ("denied", "readlink"):
    os.setgroups([])
    os.setresgid(int(sys.argv[3]), int(sys.argv[3]), int(sys.argv[3]))
    os.setresuid(int(sys.argv[3]), int(sys.argv[3]), int(sys.argv[3]))
try:
    brig.create_bwrap_jail(
        ("true",),
        processes=FakeProcesses(),
        directories=FakeChannelDirectories(),
        placeholders=FakePlaceholders(),
        **kwargs,
    )
except BaseException as error:
    cause = error.__cause__
    print(json.dumps({
        "raised": True,
        "uid": os.getuid(),
        "type": type(error).__name__,
        "module": type(error).__module__,
        "is_oserror": isinstance(error, OSError),
        "cause_is_oserror": isinstance(cause, OSError),
        "cause_errno": cause.errno if isinstance(cause, OSError) else None,
        "path": getattr(error, "path", None),
    }))
else:
    print(json.dumps({"raised": False}))
"""


@pytest.fixture
def work() -> Iterator[Path]:
    """A fresh directory under `/tmp` that `nobody` can search (pytest's own `tmp_path` lies under
    a directory only root can), with a state directory in it that `nobody` owns."""
    with tempfile.TemporaryDirectory(dir="/tmp") as made:
        root = Path(made)
        root.chmod(0o755)
        (root / "state").mkdir()
        if os.getuid() == 0:
            os.chown(root / "state", _NOBODY, _NOBODY)
        yield root


def _create_in_child(work: Path, mode: str) -> dict[str, object]:
    """Run one `create_bwrap_jail` in a child Python whose `BRIG_HOME` is `work/state`, set up per
    `mode`, and hand back what it raised."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "BRIG_HOME": str(work / "state"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    finished = subprocess.run(
        [sys.executable, "-c", _CHILD, mode, str(work), str(_NOBODY)],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr
    outcome: dict[str, object] = json.loads(finished.stdout.strip().splitlines()[-1])
    return outcome


def _assert_crossed_as_brigs_own(outcome: dict[str, object]) -> None:
    """The create failed with one of `presentation/errors.py`'s types, exported by `brig`, whose
    `__cause__` is the host's `OSError`."""
    assert outcome["raised"] is True
    assert outcome["is_oserror"] is False, f"a bare {outcome['type']} crossed the API"
    assert outcome["module"] == "brig.presentation.errors"
    assert outcome["type"] in brig.__all__
    assert outcome["cause_is_oserror"] is True


def _needs_root() -> None:
    if os.getuid() != 0:
        pytest.skip("dropping to another user needs root")


def test_a_policy_path_the_embedder_cannot_search_crosses_as_brigs_own_error(work: Path) -> None:
    """The policy names a path beneath a directory only root can search, and the embedder is
    `nobody`: `stat` is refused (`EACCES`)."""
    _needs_root()
    (work / "locked").mkdir(mode=0o700)

    outcome = _create_in_child(work, "denied")

    assert outcome["uid"] == _NOBODY
    _assert_crossed_as_brigs_own(outcome)
    assert outcome["cause_errno"] == errno.EACCES
    assert outcome["path"] == f"{work}/locked/inside"


def test_a_policy_path_that_is_a_link_loop_crosses_as_brigs_own_error(work: Path) -> None:
    """The policy names a symbolic link that leads back to itself through another: `stat` fails
    with `ELOOP`."""
    (work / "loop").symlink_to(work / "back")
    (work / "back").symlink_to(work / "loop")

    outcome = _create_in_child(work, "loop")

    _assert_crossed_as_brigs_own(outcome)
    assert outcome["cause_errno"] == errno.ELOOP
    assert outcome["path"] == f"{work}/loop"


def test_a_stdio_path_through_a_link_brig_cannot_read_crosses_as_brigs_own_error(
    work: Path,
) -> None:
    """The stdio path goes through root's `/proc/<pid>/cwd`, and the embedder is `nobody`: the
    link is there, and reading where it leads is refused (`EACCES`)."""
    _needs_root()

    outcome = _create_in_child(work, "readlink")

    assert outcome["uid"] == _NOBODY
    _assert_crossed_as_brigs_own(outcome)
    assert outcome["cause_errno"] == errno.EACCES
    assert outcome["path"] == f"/proc/{os.getpid()}/cwd/out.txt"


def test_a_supervisor_source_that_cannot_be_read_is_not_a_state_directory_failure(
    work: Path,
) -> None:
    """brig is imported from a copy whose supervisor program is then deleted: the failure is
    brig's own error, not `StateDirectoryWriteFailed`, and no script is left in the state
    directory."""
    shutil.copytree(
        _ROOT / "src" / "brig",
        work / "site" / "brig",
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    outcome = _create_in_child(work, "source")

    _assert_crossed_as_brigs_own(outcome)
    assert outcome["type"] != "StateDirectoryWriteFailed"
    assert outcome["cause_errno"] == errno.ENOENT
    assert list((work / "state").glob("brig-supervisor-*")) == []
