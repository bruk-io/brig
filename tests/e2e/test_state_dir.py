"""Tests for `infra/state_dir.py` (TASK-0006).

Decision-0001 rule 4 lets an e2e test import a `brig.infra` module directly, the
same allowance `test_supervisor_assemble.py` and `test_processes_gateway.py`
already use. These tests live here for that reason alone, not because anything
below needs a real jail, bwrap, or any slow I/O: `resolve` is pure (synthetic
`env` mappings, asserted straight against its return value, no real filesystem
touched), and `ensure`'s one real effect (`mkdir`) is exercised against a
throwaway directory, idempotently, in milliseconds -- both would read as ordinary
`tests/unit/` tests if `brig-test-layers` (`pypeeker_rules/brig.py`) let a unit
test import anything under `brig.infra` at all. It does not, so this is where a
pure function living in `infra/` gets tested instead.
"""

import tempfile
from pathlib import Path

import pytest

from brig.infra import state_dir


def test_resolve_defaults_to_home_dot_brig_when_brig_home_is_unset() -> None:
    """No `BRIG_HOME` in the given `env` -- `~/.brig`, the documented default."""
    assert state_dir.resolve(env={}) == Path.home() / ".brig"


def test_resolve_honors_brig_home_exactly_as_given_when_set_and_absolute() -> None:
    """`BRIG_HOME`, when set to an absolute path, is taken exactly as given --
    no further default-resolution logic, no joining with anything.
    """
    assert state_dir.resolve(env={"BRIG_HOME": "/custom/brig-state"}) == Path("/custom/brig-state")


def test_resolve_rejects_a_relative_brig_home() -> None:
    """A relative `BRIG_HOME` is refused, not silently accepted: this task's
    review measured that a relative value reproduces TASK-0006's original bug
    exactly on real Linux -- `BRIG_HOME=relstate` makes real bwrap fail with
    `bwrap: Can't mkdir relstate: Read-only file system`, then `JailExitUnknown`
    -- so a value that can only ever break the jail it is meant to fix is
    rejected here instead of taken "exactly as given" into a bind that cannot
    work. An earlier revision of this test blessed exactly this value as
    correct; it was not.
    """
    with pytest.raises(ValueError):
        state_dir.resolve(env={"BRIG_HOME": "relstate"})


def test_resolve_prefers_brig_home_over_the_default_even_alongside_other_vars() -> None:
    """`resolve` reads only `BRIG_HOME` out of whatever mapping it is given --
    other names present alongside it (here, a decoy `HOME`) change nothing.
    """
    env = {"HOME": "/decoy", "BRIG_HOME": "/real/brig-state"}

    assert state_dir.resolve(env=env) == Path("/real/brig-state")


def test_ensure_creates_a_missing_directory_and_returns_it() -> None:
    """`ensure`'s one real effect: a directory that does not exist yet is created,
    parents included, and the same path is handed straight back.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "nested" / "brig-state"
        assert not target.exists()

        result = state_dir.ensure(target)

        assert result == target
        assert target.is_dir()


def test_ensure_is_a_no_op_when_the_directory_already_exists() -> None:
    """A second `ensure` call on a directory `ensure` already created is not an
    error -- every process that starts a jail calls this, and only the first one
    on a given host actually creates anything.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "already-there"
        target.mkdir()

        result = state_dir.ensure(target)

        assert result == target
        assert target.is_dir()
