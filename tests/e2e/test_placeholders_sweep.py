"""TASK-0001.32: the placeholder sweep removes every finished record's directories together, so
the order the records are read in does not decide what is left, and a directory it could not
remove stays in a record for a later sweep.

Decision-0001 rule 4 lets an e2e test import one `brig.infra` module; these drive
`infra/placeholders.py` against a real filesystem with no jail, since the sweep's decisions are
about directories and records, not mounts. A dead jail is a real process that made its record
and exited.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from brig.infra import placeholders

_DEAD_HOLDER = """
import sys
from pathlib import Path
from brig.infra import placeholders
placeholders.hold(Path(sys.argv[1]), sys.argv[2], tuple(sys.argv[3:]))
"""
"""Hold the given paths as jail `argv[2]`'s and exit: an embedder that crashed before its
teardown, which leaves its record naming a process that is gone."""


def _hold_and_die(state_dir: Path, jail_id: str, *paths: str) -> None:
    subprocess.run(
        [sys.executable, "-c", _DEAD_HOLDER, str(state_dir), jail_id, *paths], check=True
    )


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


@pytest.mark.parametrize(
    ("dead_id", "live_id"),
    [("a-dead", "b-live"), ("b-dead", "a-live")],
    ids=["dead-record-read-first", "dead-record-read-last"],
)
def test_a_dead_records_directory_goes_when_a_later_record_made_directories_inside_it(
    dead_id: str, live_id: str
) -> None:
    """A crashed jail made W/.git; a later jail, finding W/.git there, made W/.git/hooks inside
    it. That jail's teardown sweeps both records, and nothing brig made is left, whichever record
    the sweep reads first."""
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as top,
        tempfile.TemporaryDirectory(dir="/tmp") as state,
    ):
        root, state_dir = Path(top), Path(state)
        (root / "kept.txt").write_text("the person's")
        before = _tree(root)
        _hold_and_die(state_dir, dead_id, f"{top}/.git")
        assert (root / ".git").is_dir()
        record = placeholders.hold(state_dir, live_id, (f"{top}/.git/hooks",))
        assert (root / ".git" / "hooks").is_dir()

        placeholders.release(state_dir, record)

        assert _tree(root) == before, "a directory brig made outlived every jail over it"
        assert not list((state_dir / "placeholders").glob("*.json"))


def test_a_directory_the_sweep_could_not_remove_is_retried_by_a_later_sweep() -> None:
    """A placeholder that is not empty when its jail goes cannot be removed then; once it is
    empty again, the next jail's teardown removes it, because a record still names it."""
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as top,
        tempfile.TemporaryDirectory(dir="/tmp") as state,
    ):
        root, state_dir = Path(top), Path(state)
        first = placeholders.hold(state_dir, "first", (f"{top}/.envrc",))
        (root / ".envrc" / "stray").write_text("")
        placeholders.release(state_dir, first)
        assert (root / ".envrc").is_dir(), "a directory that was not empty was removed"

        (root / ".envrc" / "stray").unlink()
        second = placeholders.hold(state_dir, "second", (f"{top}/secret.env",))
        placeholders.release(state_dir, second)

        assert _tree(root) == [], "the sweep forgot a directory it could not remove"
        assert not list((state_dir / "placeholders").glob("*.json"))
