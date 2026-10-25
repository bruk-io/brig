"""Tests for `infra/sockets.py` (TASK-0001.26 AC#1), on the real filesystem.

Decision-0001 rule 4 lets an e2e test import a `brig.infra` module directly, the same
allowance `test_state_dir.py` uses; `brig-test-layers` forbids a unit test from
importing anything under `brig.infra`, so the gateway's own tests live here. Every
test works inside a throwaway directory, never brig's real state directory.
"""

import stat
import tempfile
from pathlib import Path

import pytest

from brig.infra import sockets


def test_create_makes_a_private_directory_and_every_missing_parent() -> None:
    """`create` makes the leaf (and its parents) and leaves the leaf mode 0o700 --
    private to the owning user, whatever the umask said.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "nested" / "channels" / "abc"

        sockets.create(str(target))

        assert target.is_dir()
        assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_a_second_create_restores_privacy_that_something_else_widened() -> None:
    """`create` is idempotent and re-applies 0o700 each time, so a mode widened in
    between does not survive a repeated call.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "abc"
        sockets.create(str(target))
        target.chmod(0o755)

        sockets.create(str(target))

        assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_remove_deletes_the_directory_and_everything_written_inside_it() -> None:
    """The jailed command creates files (sockets) inside before destroy runs, so
    `remove` must delete a non-empty directory, not only an empty one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "abc"
        sockets.create(str(target))
        (target / "ctl").write_text("stand-in for a socket")

        sockets.remove(str(target))

        assert not target.exists()


def test_remove_of_a_missing_directory_raises_file_not_found() -> None:
    """`remove` leaves the decision to swallow an already-gone directory to its
    caller, the same split as the supervisor script's own `unlink`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            sockets.remove(str(Path(tmp) / "never-created"))
