"""E2E test for the bwrap walking skeleton (TASK-0001.03) and deadline (TASK-0001.06).

Runs the whole journey -- create a bwrap jail, run a command in it, destroy it --
through brig's public API against the real bubblewrap, with nothing faked.

This test is guarded to skip cleanly on hosts where bwrap is not available (e.g. macOS).
It will run for real in CI on Linux.
"""

import shutil

import pytest

from brig import JailWaitTimedOut, create_bwrap_jail, destroy_jail, run_jail


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_bwrap_walking_skeleton_real_journey() -> None:
    """Create, run and destroy a real bwrap jail for `true`.

    This is a real e2e test against actual bubblewrap:
    - Creates a bwrap jail through brig's public API
    - Runs `true` in it (which exits 0 and leaves no processes)
    - Destroys the jail with verified teardown (no process of the group left)
    - Asserts the exit code and verified cleanup

    On hosts without bwrap (macOS), this test skips cleanly with a clear reason.
    """
    jail = create_bwrap_jail(("true",))
    exit_code = run_jail(jail)
    destroy_jail(jail)

    assert exit_code == 0


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_bwrap_process_never_exits_times_out() -> None:
    """Run a command that never exits and verify timeout raises JailWaitTimedOut.

    This e2e test covers AC#3 for TASK-0001.06 -- running the real journey with a
    process that never exits on its own (sleep 9999), with a small deadline, confirms
    the public API raises JailWaitTimedOut instead of hanging the embedder forever.

    The test:
    - Creates a bwrap jail for `sleep 9999` (a process that never exits on its own)
    - Calls `run_jail` with a short timeout (0.5 seconds) and verifies it raises
      `JailWaitTimedOut` with the correct process
    - Destroys the jail (still required even after timeout, per api.py docstring)
    """
    jail = create_bwrap_jail(("sleep", "9999"))

    with pytest.raises(JailWaitTimedOut) as excinfo:
        run_jail(jail, timeout_s=0.5)

    assert excinfo.value.process == jail.process

    destroy_jail(jail)
