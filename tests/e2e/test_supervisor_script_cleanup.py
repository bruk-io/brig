"""E2E battery for supervisor-script cleanup (TASK-0001.21).

`presentation/api.py`'s `_supervisor_path()` used to be `functools.cache`d, so every
jail a process created after the first reused the exact same written file --
`destroy_jail` had nothing of its own to delete without also deleting a still-live
jail's own. TASK-0001.21 gives every jail its own fresh file, written by
`_supervisors_for`, and threads its exact path onto the `Jail` it returns
(`Jail.supervisor_script`) for `destroy_jail` to delete once its own teardown has
confirmed `GroupState.GONE`. This battery grades that through the public API,
against the real state directory on disk, with real bwrap jails -- the only way a
supervisor script is ever actually written at all: an explicit `supervisors=` (a
fake, in a test) short-circuits `_supervisors_for` entirely, which is why
`tests/integration/test_destroy_without_run.py`'s own fakes-based test asserts
`jail.supervisor_script is None` rather than proving any deletion.

Every test here needs a real bwrap jail, so each is guarded the same way every
other real-jail battery in this suite is: skipped cleanly where bwrap is not
installed (macOS), run for real in CI on Linux.
"""

import shutil
import sys

import pytest

from brig import create_bwrap_jail, destroy_jail, run_jail

_EXIT_CLEANLY = (sys.executable, "-c", "import sys; sys.exit(0)")


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_a_jails_own_supervisor_script_is_gone_once_destroy_jail_returns() -> None:
    """AC#3: a jail's own supervisor script is deleted from the state directory
    once its `destroy_jail` call returns successfully.
    """
    jail = create_bwrap_jail(_EXIT_CLEANLY)
    script = jail.supervisor_script
    assert script is not None
    assert script.is_file()

    run_jail(jail)
    destroy_jail(jail)

    assert not script.exists()


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_destroying_one_of_two_jails_leaves_the_others_own_file_and_jail_alone() -> None:
    """AC#4: destroying one of two jails a process created does not delete the
    other, still-live jail's own supervisor script -- and that other jail still
    runs correctly afterward.
    """
    first = create_bwrap_jail(_EXIT_CLEANLY)
    second = create_bwrap_jail((sys.executable, "-c", "import sys; sys.exit(7)"))
    assert first.supervisor_script is not None
    assert second.supervisor_script is not None
    assert first.supervisor_script != second.supervisor_script
    assert first.supervisor_script.is_file()
    assert second.supervisor_script.is_file()

    run_jail(first)
    destroy_jail(first)

    assert not first.supervisor_script.exists()
    assert second.supervisor_script.is_file()  # untouched by the other jail's teardown

    exit_code = run_jail(second)
    destroy_jail(second)

    assert exit_code == 7
    assert not second.supervisor_script.exists()


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_many_create_destroy_cycles_leave_zero_accumulated_files() -> None:
    """AC#5: many create/destroy cycles in one process leave zero accumulated
    supervisor scripts afterward -- not merely bounded growth, the pre-fix
    behaviour of one `functools.cache`d file shared (and kept) across every jail
    a process created.
    """
    scripts = []
    for _ in range(25):
        jail = create_bwrap_jail(_EXIT_CLEANLY)
        assert jail.supervisor_script is not None
        scripts.append(jail.supervisor_script)
        run_jail(jail)
        destroy_jail(jail)

    assert len(set(scripts)) == len(scripts)  # every cycle really did get its own file
    assert not any(script.exists() for script in scripts)


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_destroy_before_run_still_deletes_the_jails_own_supervisor_script() -> None:
    """AC#6: `destroy_jail` called before `run_jail` ever ran still deletes the
    jail's own real supervisor script, once teardown confirms `GroupState.GONE` --
    the same shape `tests/integration/test_destroy_without_run.py` covers against
    fakes, which never write a real file to delete in the first place.
    """
    jail = create_bwrap_jail((sys.executable, "-c", "import time; time.sleep(30)"))
    script = jail.supervisor_script
    assert script is not None
    assert script.is_file()

    destroy_jail(jail)

    assert not script.exists()
