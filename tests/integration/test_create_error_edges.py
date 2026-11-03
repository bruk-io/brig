"""TASK-0046's repro: three edges where `create_bwrap_jail` still lets an error out that is not
brig's own, hides the error that made it fail, or leaves a process it spawned running.

1. Before the start, preparing brig's state directory and writing the supervisor script into it
   can raise the host's bare `OSError`, past the driver exception boundary: an embedder would
   have to handle infra's errors. Each of the three host failures is made real, in a child
   Python with its own `BRIG_HOME` (the parent's state directory is resolved once per process,
   and shared with every other jail on this host): the state directory under a regular file, a
   state directory whose empty directory is not empty, and a file size limit that stops the
   script's write.
2. `dismantle` says it raises nothing, but an `OSError` from the kill ladder or from closing the
   supervisor escapes it, and replaces the failed step's own error.
3. A supervisor port whose start spawned the supervisor and then failed leaves `process` unset,
   so the kill ladder never runs on what it spawned.

The world is faked at infra's edge (decision-0001 rule 5); each test catches whatever crosses and
asserts on it, so each fails on what it pins, not on an error it did not expect.
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from tests.integration.fakes import FakePlaceholders, FakeProcesses, FakeSupervisors

import brig
from brig import JailSpawnFailed, JailTeardownFailed, PlaceholdersFailed, create_bwrap_jail

_SUPERVISOR_PID = 2000
"""`FakeSupervisors`'s first fabricated pid, and its pgid."""

_ROOT = Path(__file__).resolve().parents[2]

_CHILD = """
import json, resource, signal, sys
from tests.integration.fakes import FakeChannelDirectories, FakePlaceholders, FakeProcesses
import brig

if sys.argv[1] == "fsize":
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (1024, resource.getrlimit(resource.RLIMIT_FSIZE)[1])
    )
try:
    brig.create_bwrap_jail(
        ("true",),
        processes=FakeProcesses(),
        directories=FakeChannelDirectories(),
        placeholders=FakePlaceholders(),
    )
except BaseException as error:
    print(json.dumps({
        "raised": True,
        "type": type(error).__name__,
        "module": type(error).__module__,
        "is_oserror": isinstance(error, OSError),
        "cause_is_oserror": isinstance(error.__cause__, OSError),
    }))
else:
    print(json.dumps({"raised": False}))
"""


def _create_in_child(brig_home: Path, limit: str = "") -> dict[str, object]:
    """Run one `create_bwrap_jail` in a child Python whose `BRIG_HOME` is `brig_home`, under
    `limit` (`"fsize"`: a 1 KiB file size limit), and hand back what it raised."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "BRIG_HOME": str(brig_home),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    finished = subprocess.run(
        [sys.executable, "-c", _CHILD, limit],
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
    """The create failed with one of `presentation/errors.py`'s types, exported by `brig`,
    whose `__cause__` is the host's `OSError`."""
    assert outcome["raised"] is True
    assert outcome["is_oserror"] is False, f"a bare {outcome['type']} crossed the API"
    assert outcome["module"] == "brig.presentation.errors"
    assert outcome["type"] in brig.__all__
    assert outcome["cause_is_oserror"] is True


def test_a_state_directory_that_cannot_be_made_crosses_as_brigs_own_error(
    tmp_path: Path,
) -> None:
    """`BRIG_HOME` lies under a regular file, so the state directory cannot be made."""
    (tmp_path / "file").write_text("")

    _assert_crossed_as_brigs_own(_create_in_child(tmp_path / "file" / "state"))


def test_an_empty_directory_that_is_not_empty_crosses_as_brigs_own_error(
    tmp_path: Path,
) -> None:
    """The state directory's empty directory already holds a file, so it cannot be prepared."""
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "planted").write_text("")

    _assert_crossed_as_brigs_own(_create_in_child(tmp_path))


def test_a_supervisor_script_that_cannot_be_written_crosses_as_brigs_own_error(
    tmp_path: Path,
) -> None:
    """A 1 KiB file size limit stops the supervisor script's write part way (`EFBIG`)."""
    _assert_crossed_as_brigs_own(_create_in_child(tmp_path, "fsize"))


def test_a_teardown_that_raises_does_not_hide_the_steps_error() -> None:
    """The attach fails once the supervisor has started, and the teardown that follows has its
    TERM refused: the group was never verified gone, so `JailTeardownFailed` names the
    supervisor, the attach's `PlaceholdersFailed` is its cause, and the refused signal is
    attached to that, not raised in its place. The placeholders a live jail may still mount
    over are kept."""
    processes = FakeProcesses(alive_checks=1, fail_signal=True)
    supervisors = FakeSupervisors()
    placeholders = FakePlaceholders(fail_attach=True)

    with pytest.raises(BaseException) as raised:
        create_bwrap_jail(
            ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
        )

    assert isinstance(raised.value, JailTeardownFailed), repr(raised.value)
    assert raised.value.process.pid == _SUPERVISOR_PID
    step = raised.value.__cause__
    assert isinstance(step, PlaceholdersFailed)
    assert any("signal was refused" in note for note in getattr(step, "__notes__", ()))
    assert supervisors.closed == [_SUPERVISOR_PID]
    assert placeholders.released == []


def test_a_close_that_raises_does_not_hide_the_steps_error() -> None:
    """The attach fails, the teardown reads the group gone after TERM, and closing the
    supervisor's pipe raises: the attach's own `PlaceholdersFailed` still propagates, with the
    close's failure attached to it, and the placeholders are released."""
    processes = FakeProcesses(alive_checks=1)
    supervisors = FakeSupervisors(fail_close=True)
    placeholders = FakePlaceholders(fail_attach=True)

    with pytest.raises(BaseException) as raised:
        create_bwrap_jail(
            ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
        )

    assert isinstance(raised.value, PlaceholdersFailed), repr(raised.value)
    notes = getattr(raised.value, "__notes__", ())
    assert any("pipe could not be closed" in note for note in notes)
    assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
    assert placeholders.released == [placeholders.record]


def test_a_start_that_spawned_then_failed_tears_the_spawned_supervisor_down() -> None:
    """The port's start spawned the supervisor and then failed: `JailSpawnFailed` still
    propagates, and before it does the spawned supervisor's group was verified, sent TERM,
    verified gone, its pid released and its pipe closed."""
    processes = FakeProcesses(alive_checks=1)
    supervisors = FakeSupervisors(fail_after_start=True)
    placeholders = FakePlaceholders()

    with pytest.raises(BaseException) as raised:
        create_bwrap_jail(
            ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
        )

    assert isinstance(raised.value, JailSpawnFailed), repr(raised.value)
    assert supervisors.spawned == [_SUPERVISOR_PID]
    assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
    assert processes.released == [_SUPERVISOR_PID]
    assert supervisors.closed == [_SUPERVISOR_PID]
    assert placeholders.released == [placeholders.record]
