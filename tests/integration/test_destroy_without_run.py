"""Integration test for `destroy_jail` tearing a jail down that `run_jail` never
waited on at all (TASK-0001.15 step 5).

`presentation/api.py`'s own `destroy_jail` docstring states this exact claim: it
"also releases whatever `supervisors` is still holding open for `jail`'s
supervisor... a no-op if `run_jail` already did, by way of a terminal `await_done`
outcome, so a jail destroyed without ever being run still gets that cleaned up
here." No existing integration test drives that path -- `test_walking_skeleton.py`
and every other integration test under this task always calls `run_jail` before
`destroy_jail` -- so the unconditional `supervisors.close(...)` call this docstring
promises has never actually been exercised with `await_done` never having run at
all. Runs the create-then-destroy half of the journey through brig's public API,
with `FakeSupervisors` standing in for the world. Nothing inside brig's own code is
faked or patched (rule 5); only the world at the edge is.
"""

from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import create_bwrap_jail, destroy_jail


def test_destroy_jail_closes_the_supervisor_even_when_run_jail_never_ran() -> None:
    """`destroy_jail` still closes the jail's supervisor when `run_jail` was never
    called at all, not only when it ran and resolved `await_done` to a terminal
    outcome first.
    """
    processes = FakeProcesses()
    supervisors = FakeSupervisors()

    jail = create_bwrap_jail(("sleep", "9999"), processes=processes, supervisors=supervisors)
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    # run_jail was never called, so await_done was never invoked -- close is the
    # only thing that ever touches the supervisor's own open pipe here.
    assert supervisors.awaited == []
    assert supervisors.closed == [jail.process.pid]
    # Teardown's own ladder still ran against the jail's one process regardless
    # (decision-0002: the supervisor's pid/pgid, not the real command's).
    assert processes.checked == [jail.process.pgid]
