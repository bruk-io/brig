"""E2E battery for supervisor-script cleanup (TASK-0001.21, TASK-0012).

`presentation/api.py`'s `_supervisor_path()` used to be `functools.cache`d, so every
jail a process created after the first reused the exact same written file --
`destroy_jail` had nothing of its own to delete without also deleting a still-live
jail's own. TASK-0001.21 gives every jail its own fresh file, written by
`_supervisors_for`, and threads its exact path onto the `Jail` it returns
(`Jail.supervisor_script`) for `destroy_jail` to delete once its own teardown has
run. This battery grades that through the public API, against the real state
directory on disk, with real bwrap jails -- the only way a supervisor script is
ever actually written at all: an explicit `supervisors=` (a fake, in a test)
short-circuits `_supervisors_for` entirely, which is why
`tests/integration/test_destroy_without_run.py`'s own fakes-based test asserts
`jail.supervisor_script is None` rather than proving any deletion.

Every test here but the last needs a real bwrap jail, so each of those is guarded
the same way every other real-jail battery in this suite is: skipped cleanly where
bwrap is not installed (macOS), run for real in CI on Linux. The last test
(TASK-0012 AC#1/AC#2) needs the opposite host shape -- a real, measured supervisor-
spawn failure, which this task's own filing found only where `bwrap` is genuinely
missing (this macOS host: 22 orphaned scripts already sitting in `~/.brig` before
the fix, from exactly this path having been hit repeatedly by prior test/agent
activity). `link._start` spawns the supervisor through `infra.processes.spawn`
directly, not through any port `create_bwrap_jail` lets a test inject (TASK-0001.15
step 4: that call is never routed through the `ProcessPort`/`SupervisorPort` an
explicit `supervisors=` replaces, since an explicit `supervisors` skips
`_supervisors_for` -- and the real file on disk -- entirely), so there is no way to
fake this failure from inside brig's own public API; the host's own `bwrap`
binary, present or absent, is genuinely the only lever. A Linux host with `bwrap`
installed was measured (TASK-0012's own implementation notes) to never reach a
"not found" failure at all -- `os.posix_spawnp` falls back to running `/bin/sh -c`
on a command it cannot resolve rather than raising, a real, measured gap between
this module's own docstring and Linux's actual behaviour, filed separately. So
this test runs only where the real thing it proves actually happens
(`python-tests-e2e`: "It runs only where the real thing exists... never counted as
a pass"), the mirror image of every other test in this file.
"""

import shutil
import sys

import pytest

from brig import JailSpawnFailed, create_bwrap_jail, destroy_jail, run_jail
from brig.infra.state_dir import ensure as _ensure_state_dir
from brig.infra.state_dir import resolve as _resolve_state_dir

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


@pytest.mark.skipif(
    shutil.which("bwrap") is not None,
    reason="needs a host where bwrap is genuinely missing (macOS); on a host "
    "where bwrap is installed the supervisor spawns and no Jail-less failure "
    "occurs at all, so this is the mirror image of this file's other skips",
)
def test_a_run_that_fails_before_a_jail_is_ever_returned_does_not_leak_its_script() -> None:
    """TASK-0012 AC#1/AC#2: `create_bwrap_jail`'s own `run` raising before a `Jail`
    is ever constructed and returned -- no `Jail` exists for any later
    `destroy_jail` call to delete the script through -- still does not leave the
    freshly-written supervisor script behind.

    The real, measured shape this task's own filing found on this exact host:
    `bwrap` is not installed, so the supervisor's own spawn fails with a real
    `FileNotFoundError`, wrapped by `infra.processes.spawn` into `SpawnError`, by
    `infra.supervisor.link._start` into `SupervisorSpawnError`, and by
    `presentation/drivers/bwrap.py`'s own driver into `JailSpawnFailed` -- all
    before `create_bwrap_jail` ever constructs the `Jail` it would otherwise
    return.
    """
    state_dir = _ensure_state_dir(_resolve_state_dir())
    before = set(state_dir.iterdir())

    with pytest.raises(JailSpawnFailed):
        create_bwrap_jail(_EXIT_CLEANLY)

    after = set(state_dir.iterdir())
    assert after == before  # the script this call wrote did not survive it
