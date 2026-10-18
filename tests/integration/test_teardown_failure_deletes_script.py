"""Integration test for TASK-0012's second leak shape: a `destroy_jail` call whose
own kill ladder never reaches `GroupState.GONE` (`JailTeardownFailed`) used to leave
the jail's own supervisor script behind forever, since the deletion sat behind an
`if state is not GroupState.GONE: raise` that returned before ever reaching it.

`destroy_jail`'s own docstring has the reasoning for why deleting the script here is
still safe even though the jail's group may still genuinely be alive: the file only
ever needed to not be deleted *before* it was exec'd, never while a process still
runs from it, and by the time teardown's own verify has run at all, any exec that was
ever going to happen already happened.

A `Jail` built through the public API's own `create_bwrap_jail` against fakes, the
same way `tests/integration/test_destroy_without_run.py` already does (decision-0001
rule 4: an integration test imports `brig`'s public API or `tests.integration.fakes`,
never `brig.domain` directly) -- its own `supervisor_script` is always `None` with an
explicit `supervisors` given (`create_bwrap_jail`'s own docstring), so this replaces
it with a real file on disk before tearing it down. `FakeProcesses(alive=True)`
stands in for a process group the kill ladder's own escalating signals never
actually bring down, the one thing this test fakes at the world's edge (rule 5).
"""

import dataclasses
from pathlib import Path

import pytest
from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import JailTeardownFailed, create_bwrap_jail, destroy_jail


def test_a_failed_teardown_still_deletes_the_jails_own_supervisor_script(
    tmp_path: Path,
) -> None:
    """`JailTeardownFailed` (the kill ladder's last verify still found the group
    alive) still deletes `jail.supervisor_script`, and the exception still
    propagates unchanged.
    """
    script = tmp_path / "brig-supervisor-fake.py"
    script.write_text("# stands in for a real supervisor script\n")
    processes = FakeProcesses(alive=True)
    supervisors = FakeSupervisors()
    jail = create_bwrap_jail(("true",), processes=processes, supervisors=supervisors)
    jail = dataclasses.replace(jail, supervisor_script=script)

    with pytest.raises(JailTeardownFailed) as exc_info:
        destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert exc_info.value.process == jail.process
    assert not script.exists()
    # The supervisor's own open pipe is still released even though teardown failed
    # (`destroy_jail`'s own docstring: a no-op if `run_jail` already did).
    assert supervisors.closed == [jail.process.pid]
