"""TASK-0046 beyond its repro (`test_create_error_edges.py`): which of brig's types each edge
crosses as, and the teardown paths the repro does not reach.

- A host refusal before the start is `StateDirectoryWriteFailed`, naming what could not be made
  or written, and a supervisor script written in part does not survive it. As in the repro, each
  failure is real, in a child Python with its own `BRIG_HOME`.
- A start that spawned and then failed, whose teardown cannot end the group, is
  `JailTeardownFailed` from that `JailSpawnFailed`, and the placeholders are kept.
- `destroy_jail` runs the same `dismantle`: a kill ladder that raises is `JailTeardownFailed`
  from that error, never the bare error, and a close that raises once the group reads gone is
  swallowed like every other cleanup.

The world is faked at infra's edge (decision-0001 rule 5).
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from tests.integration.fakes import FakePlaceholders, FakeProcesses, FakeSupervisors

from brig import (
    JailSpawnFailed,
    JailTeardownFailed,
    Process,
    create_bwrap_jail,
    destroy_jail,
)

_SUPERVISOR_PID = 2000
"""`FakeSupervisors`'s first fabricated pid, and its pgid."""

_ROOT = Path(__file__).resolve().parents[2]

_CHILD = """
import json, os, resource, signal, sys
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
except brig.StateDirectoryWriteFailed as error:
    home = os.environ["BRIG_HOME"]
    scripts = (
        sorted(name for name in os.listdir(home) if name.startswith("brig-supervisor-"))
        if os.path.isdir(home)
        else []
    )
    print(json.dumps({"path": error.path, "cause": type(error.__cause__).__name__,
                      "scripts": scripts}))
"""


def _refused_in_child(brig_home: Path, limit: str = "") -> dict[str, object]:
    """Run one `create_bwrap_jail` in a child Python whose `BRIG_HOME` is `brig_home`, under
    `limit` (`"fsize"`: a 1 KiB file size limit), and hand back its `StateDirectoryWriteFailed`:
    the path it names, its cause's type, and the supervisor scripts left in `brig_home`."""
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
    assert finished.stdout.strip(), "the create did not raise StateDirectoryWriteFailed"
    outcome: dict[str, object] = json.loads(finished.stdout.strip().splitlines()[-1])
    return outcome


def test_a_state_directory_that_cannot_be_made_names_it(tmp_path: Path) -> None:
    """`BRIG_HOME` under a regular file: the state directory is what could not be made."""
    (tmp_path / "file").write_text("")
    home = tmp_path / "file" / "state"

    outcome = _refused_in_child(home)

    assert outcome["path"] == str(home)
    assert outcome["cause"] == "NotADirectoryError"


def test_an_empty_directory_that_is_not_empty_names_it(tmp_path: Path) -> None:
    """The empty directory holds a file: it is what could not be prepared, and no supervisor
    script was written."""
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "planted").write_text("")

    outcome = _refused_in_child(tmp_path)

    assert outcome["path"] == f"{tmp_path}/empty"
    assert outcome["cause"] == "OSError"
    assert outcome["scripts"] == []


def test_a_script_written_in_part_is_removed(tmp_path: Path) -> None:
    """The file size limit stops the script's write after 1 KiB: the error names the state
    directory, and the part written is gone."""
    outcome = _refused_in_child(tmp_path, "fsize")

    assert outcome["path"] == str(tmp_path)
    assert outcome["cause"] == "OSError"
    assert outcome["scripts"] == []


def test_a_spawned_then_failed_start_hands_back_what_it_spawned() -> None:
    """`JailSpawnFailed` names the supervisor that was spawned, and it was torn down."""
    processes = FakeProcesses(alive_checks=1)
    supervisors = FakeSupervisors(fail_after_start=True)

    with pytest.raises(JailSpawnFailed) as raised:
        create_bwrap_jail(("server",), processes=processes, supervisors=supervisors)

    assert raised.value.process == Process(pid=_SUPERVISOR_PID, pgid=_SUPERVISOR_PID)
    assert processes.released == [_SUPERVISOR_PID]


def test_a_spawned_then_failed_start_whose_teardown_fails_keeps_the_placeholders() -> None:
    """The spawned supervisor's group survives TERM and KILL: `JailTeardownFailed` names it,
    the start's `JailSpawnFailed` is its cause, and the placeholders are kept."""
    processes = FakeProcesses(alive=True)
    supervisors = FakeSupervisors(fail_after_start=True)
    placeholders = FakePlaceholders()

    with pytest.raises(JailTeardownFailed) as raised:
        create_bwrap_jail(
            ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
        )

    assert raised.value.process.pid == _SUPERVISOR_PID
    assert isinstance(raised.value.__cause__, JailSpawnFailed)
    assert processes.signalled == [
        (_SUPERVISOR_PID, signal.SIGTERM),
        (_SUPERVISOR_PID, signal.SIGKILL),
    ]
    assert supervisors.closed == [_SUPERVISOR_PID]
    assert placeholders.released == []


def test_destroy_jail_whose_ladder_raises_is_a_teardown_failure() -> None:
    """The kill ladder's TERM is refused: `destroy_jail` raises `JailTeardownFailed` from the
    refusal, still closes the supervisor, and keeps the placeholders of a group it never
    verified gone."""
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    placeholders = FakePlaceholders()
    jail = create_bwrap_jail(
        ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
    )
    teardown = FakeProcesses(alive_checks=1, fail_signal=True)

    with pytest.raises(JailTeardownFailed) as raised:
        destroy_jail(jail, processes=teardown, placeholders=placeholders)

    assert isinstance(raised.value.__cause__, PermissionError)
    assert supervisors.closed == [_SUPERVISOR_PID]
    assert placeholders.released == []


def test_destroy_jail_whose_close_raises_once_the_group_is_gone_returns() -> None:
    """The group reads gone after TERM and the supervisor's close raises: the jail is torn
    down, so `destroy_jail` returns, and the placeholders are released."""
    processes = FakeProcesses()
    supervisors = FakeSupervisors(fail_close=True)
    placeholders = FakePlaceholders()
    jail = create_bwrap_jail(
        ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
    )
    processes.alive_checks = 1

    destroy_jail(jail, processes=processes, placeholders=placeholders)

    assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
    assert supervisors.closed == [_SUPERVISOR_PID]
    assert placeholders.released == [placeholders.record]
