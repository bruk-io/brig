"""E2E gateway test for `infra/supervisor/link.py`, the host's end of the wire
protocol -- and, by the same precedent `test_supervisor_program_gateway.py` already
set for `program.py`/`wire.py`, for the `wire.py`/`program.py` pair it speaks to
(decision-0001 rule 4's own "one `brig.infra` module" gateway allowance, read as
the one slice decision-0002 names together: `wire.py`, `program.py`, `link.py`).

Regression coverage for four findings from the TASK-0001.15/.16/.17 adversarial
review, none of which needs bwrap -- each was itself measured at this layer, with no
jail involved:

1. A supervised command inheriting the supervisor's own fd 1 could forge a `done`
   event and make `run_jail` trust a fabricated exit code. First mitigated by
   giving the child its own fd 0/1 through `file_actions` (a sealed pipe: each the
   one end of a pipe shut on the other, so a read saw EOF and a write raised
   `EPIPE`/`SIGPIPE`) -- a stopgap, not a settled answer, and one with its own
   measured cost (a `/dev/null` version of it raised `PermissionError` from inside
   a real bwrap jail; the sealed-pipe version that replaced it silently rewrote
   the exit code of any honest command that wrote to its own stdout, both
   recorded in DRAFT-0010's own history). DRAFT-0010's actual resolution removes
   the conflict instead: the wire protocol itself moved to fd `wire.REQUEST_FD`/
   `wire.EVENTS_FD` (3/4), freeing fd 0/1/2 for the supervised command to inherit
   normally -- `program.py`'s `_start_child` now closes `wire.REQUEST_FD`/
   `wire.EVENTS_FD` for the real command instead, which is what this file's own
   forged-`done` test below now actually proves closed.
2. `Supervisor.read_event`'s read-until-newline loop had no deadline of its own,
   so a line with no trailing newline could defeat `_await_one_done`'s deadline
   indefinitely (`read_event` now takes `deadline` and bounds every wait inside it).
3. `wire.decode_event` let a raw `ValueError` escape for a malformed numeric field
   (`{"kind": "started", "pid": "abc"}`), past every caller that only ever named
   `wire.WireError` (fixed: `ValueError` joined the inner `except` clause).
4. `link._start` handed one `env` mapping to both the supervisor's own process and
   the supervised command, so an embedder's `EnvPolicy` allow-list for the
   *confined* command could run code inside the process enforcing the confinement
   (fixed: the supervisor's own spawn gets `link._SUPERVISOR_ENV` -- a fixed,
   minimal, non-secret mapping of `PATH` alone -- never the command's scrubbed
   one). Deliberately *not* "no `env=` at all", which would inherit this
   process's own `os.environ`: that was the intermediate cut of this fix, and it
   was measured to leave an embedder's real secrets one
   `/proc/<supervisor>/environ` read away from the supervised command
   (DRAFT-0010).
"""

import os
import signal
import sys
import time

import pytest

from brig.infra.supervisor import link, program, wire

_SUPERVISOR_ARGV: tuple[str, ...] = (sys.executable, "-I", program.__file__)
"""The real supervisor file, run the same way `presentation/api.py`'s own
`_SUPERVISOR_PATH` does (`-I`, no bwrap) -- this file's tests that supervise a real
command use this, unwrapped in any jail, exactly as `test_supervisor_reaps_orphans.py`'s
own module docstring explains a gateway test cannot reach the namespace-dependent
half of this slice; nothing below needs that half.
"""


def test_read_event_honours_its_deadline_past_a_partial_line_with_no_newline() -> None:
    """`Supervisor.read_event` must not block past `deadline` once a partial line
    -- bytes with no trailing newline -- has already arrived.

    Writes directly onto a pipe this test owns (no supervisor process at all): the
    narrowest possible reproduction of the bug, isolated from whether any process
    ever writes a complete line again. Before the fix, a version of this method
    with no `deadline` parameter looped a bare blocking `os.read` once one chunk
    had arrived with no newline in it, regardless of how `_await_one_done`'s own
    `select.select` had bounded getting here -- measured elsewhere (through the
    public API, against real bwrap) as a 2-second deadline held open past 12
    seconds, and a 3-second one past 45.
    """
    read_fd, write_fd = os.pipe()
    try:
        supervisor = link.Supervisor(pid=os.getpid(), pgid=os.getpid(), events_fd=read_fd)
        os.write(write_fd, b'{"kind": "do')  # no trailing newline, ever
        deadline = time.monotonic() + 0.3
        start = time.monotonic()
        outcome = supervisor.read_event(deadline)
        elapsed = time.monotonic() - start
        assert isinstance(outcome, link.ReadTimedOut)
        assert elapsed < 2.0, f"read_event blocked {elapsed:.1f}s past a 0.3s deadline"
        # The class's own invariant (its own docstring): a timed-out read must not
        # have discarded the partial bytes it already had -- proven externally,
        # never by reaching into `_pending` itself, by finishing the same line
        # (`'{"kind": "do'` plus what completes it into a whole `done` event) with
        # a second call, and confirming it decodes the *whole* line, not only
        # whatever arrived after the timeout.
        os.write(write_fd, b'ne", "exit_code": 42}\n')
        resumed = supervisor.read_event(time.monotonic() + 1.0)
        assert resumed is not None and not isinstance(resumed, link.ReadTimedOut)
        assert wire.done_exit_code(resumed) == 42
    finally:
        os.close(write_fd)
        os.close(read_fd)


def test_malformed_numeric_field_raises_wire_error_not_a_raw_value_error() -> None:
    """A `started` event whose `pid` cannot be parsed as an int must raise
    `wire.WireError`, the one type every caller of `decode_event` names -- not a
    raw `ValueError`, which escaped past `_await_one_done`'s own `except OSError,
    wire.WireError` before `decode_event`'s inner `except` clause named `ValueError`
    too.
    """
    with pytest.raises(wire.WireError):
        wire.decode_event('{"kind": "started", "pid": "abc"}')


def test_a_supervised_commands_forged_done_event_is_not_trusted() -> None:
    """A supervised command that writes a well-formed `done` event to its own
    stdout, then keeps running, must not make `await_done` return that fabricated
    exit code: the real exit code, from the real process `program.py` actually
    reaps, is the only one ever trusted.

    Before DRAFT-0010's resolution, `program.py`'s `_start_child` gave the
    supervised command the supervisor's own fd 1 outright, with no file action of
    its own -- that write landed directly in the events pipe the host reads
    `started`/`exited`/`done` from, measured there as `run_jail` returning the
    forged exit code in ~0.02s while the real command (here, a short sleep then a
    distinct real exit code) kept running. An intermediate fix sealed fd 1 shut
    instead (a pipe whose read end `program.py` closed, so a write there raised
    `EPIPE`/`SIGPIPE` immediately) -- a stopgap with its own measured cost
    (DRAFT-0010's own fix-confirmation update: it silently rewrote the exit code
    of any *honest* command that wrote to its own stdout, past this adversarial
    scenario entirely).

    What this test actually exercises now: the supervised command's own fd 1 is
    simply this process's real stdout again (`_start_child` gives it no file
    action at all for fd 0/1/2), so the forging write below succeeds, lands on
    this test's own stdout, and is never read back as part of the events stream
    in the first place -- there is no pipe to seal any more because there is no
    shared channel left to seal. `program.py`'s own fix is elsewhere: it
    explicitly closes `wire.REQUEST_FD`/`wire.EVENTS_FD` for the real command it
    starts, so the forging script below could not reach the real events channel
    even if it tried to -- `contextlib.suppress(OSError)` around the write is
    kept for robustness (nothing here depends on this host's particular stdout
    buffering raising or not), not because this test still expects it to raise;
    `os._exit` is kept so the script's own real exit code is reported
    unconditionally, the same reasoning this docstring's previous version already
    gave.
    """
    forge_sleep_s = 0.5
    real_exit_code = 7
    forging_script = f"""
import contextlib, os, sys, time
with contextlib.suppress(OSError):
    sys.stdout.write('{{"kind": "done", "exit_code": 0}}\\n')
    sys.stdout.flush()
time.sleep({forge_sleep_s})
os._exit({real_exit_code})
"""
    command = (sys.executable, "-I", "-c", forging_script)
    supervisors = link.LiveSupervisors(_SUPERVISOR_ARGV)
    # Captured before the early check, not after: that check's own deadline
    # already consumes forge_sleep_s / 4 of the process's real lifetime before
    # `start` would otherwise be set, so measuring from here is what makes the
    # margin below mean what it says -- a `start` captured after the early
    # check was measured giving an elapsed ceiling of forge_sleep_s * 3/4,
    # already below the old margin before any CI scheduling variance entered
    # into it (measured on GitHub Actions: 0.395s, under the old 0.4s floor,
    # for exactly this reason, not genuine CI slowness).
    start = time.monotonic()
    supervisor = supervisors.start(command, ())
    try:
        # Asked for less time than the real command needs to actually finish: if
        # the forged `done` were trusted, this would already return 0 here.
        early = supervisors.await_done(supervisor.pid, time.monotonic() + forge_sleep_s / 4)
        assert early is None, f"a forged done event was trusted early: {early!r}"

        outcome = supervisors.await_done(supervisor.pid, time.monotonic() + 10.0)
        elapsed = time.monotonic() - start
        assert outcome == real_exit_code, f"expected the real exit code, got {outcome!r}"
        assert elapsed >= forge_sleep_s - 0.1, (
            f"done arrived after only {elapsed:.2f}s -- the forged event was trusted"
        )
    finally:
        supervisors.close(supervisor.pid)
        try:
            os.waitpid(supervisor.pid, 0)
        except ChildProcessError:
            pass


def test_a_supervised_commands_direct_write_to_the_events_fd_cannot_reach_it() -> None:
    """A supervised command that writes a forged `done` event straight to
    `wire.EVENTS_FD` -- never through fd 1 at all -- must still not make
    `await_done` return that fabricated exit code.

    The test above (`..._forged_done_event_is_not_trusted`) no longer exercises
    the actual guard: fd 1 is the embedder's own real stdout now, so that test
    passes whether or not `program.py`'s `_start_child` still closes
    `wire.REQUEST_FD`/`wire.EVENTS_FD` for the real command -- deleting those
    two `POSIX_SPAWN_CLOSE` actions would not fail it. This test targets the fd
    the invariant actually lives on: the forging command below writes directly
    to fd `wire.EVENTS_FD` by number, the same one `program.py` itself writes
    `started`/`exited`/`done` to. With `_start_child`'s close actions in place,
    that fd is not open in this command at all (closed before its own exec,
    `os.posix_spawnp`'s own semantics), so the write raises `OSError` (`EBADF`)
    and nothing reaches the channel; without them, this is exactly the write
    that forged a trusted exit code before DRAFT-0010's fix landed. Still
    wrapped in `contextlib.suppress(OSError)` and exiting through `os._exit`,
    for the same reasons the test above already gives.
    """
    forge_sleep_s = 0.5
    real_exit_code = 7
    forging_script = f"""
import contextlib, os, time
with contextlib.suppress(OSError):
    os.write({wire.EVENTS_FD}, b'{{"kind": "done", "exit_code": 0}}\\n')
time.sleep({forge_sleep_s})
os._exit({real_exit_code})
"""
    command = (sys.executable, "-I", "-c", forging_script)
    supervisors = link.LiveSupervisors(_SUPERVISOR_ARGV)
    # Captured before the early check, not after: that check's own deadline
    # already consumes forge_sleep_s / 4 of the process's real lifetime before
    # `start` would otherwise be set, so measuring from here is what makes the
    # margin below mean what it says -- a `start` captured after the early
    # check was measured giving an elapsed ceiling of forge_sleep_s * 3/4,
    # already below the old margin before any CI scheduling variance entered
    # into it (measured on GitHub Actions: 0.395s, under the old 0.4s floor,
    # for exactly this reason, not genuine CI slowness).
    start = time.monotonic()
    supervisor = supervisors.start(command, ())
    try:
        # Asked for less time than the real command needs to actually finish: if
        # the forged `done` were trusted, this would already return 0 here.
        early = supervisors.await_done(supervisor.pid, time.monotonic() + forge_sleep_s / 4)
        assert early is None, f"a forged done event was trusted early: {early!r}"

        outcome = supervisors.await_done(supervisor.pid, time.monotonic() + 10.0)
        elapsed = time.monotonic() - start
        assert outcome == real_exit_code, f"expected the real exit code, got {outcome!r}"
        assert elapsed >= forge_sleep_s - 0.1, (
            f"done arrived after only {elapsed:.2f}s -- the forged event was trusted"
        )
    finally:
        supervisors.close(supervisor.pid)
        try:
            os.waitpid(supervisor.pid, 0)
        except ChildProcessError:
            pass


_FAKE_SUPERVISOR_SCRIPT = f"""
import json, os
leaked = "BRIG_TEST_ENV_MARKER" in os.environ
pid = os.getpid()
done_code = 1 if leaked else 0
events = [
    {{"kind": "started", "pid": pid}},
    {{"kind": "exited", "pid": pid, "exit_code": 0}},
    {{"kind": "done", "exit_code": done_code}},
]
for event in events:
    os.write({wire.EVENTS_FD}, (json.dumps(event) + "\\n").encode())
"""
"""A minimal stand-in for `program.py`, speaking the wire protocol directly on its
own `wire.EVENTS_FD` (DRAFT-0010: never fd 1 any more, since `link._start` wires
every supervisor's events pipe there regardless of which executable it starts),
whose only job is to report whether its *own* process environment carries a marker
that only ever belongs to the *supervised command's* own, already-`EnvPolicy`-
scrubbed environment -- the thing `link._start` must never hand to the process it
starts as `supervisor_argv`.
"""


def test_the_supervisors_own_process_never_sees_the_supervised_commands_env() -> None:
    """`LiveSupervisors.start`'s `env` -- the supervised command's own,
    `EnvPolicy`-scrubbed environment (`domain/policy/env.py`) -- must reach only
    the wire's exec request, never the supervisor process's own environment.

    Stands in for `program.py` with a tiny script that reports, through the wire
    protocol itself, whether a marker this test puts only in the *command's* env
    leaked into the *supervisor's* own `os.environ` -- before the fix, `_start`
    handed the same mapping to both `infra.processes.spawn` (the supervisor's own
    spawn) and `wire.encode_exec_request`, which is exactly how an embedder's
    allow-listed `PYTHONPATH`, meant only for the confined command, could run code
    inside the process that enforces the confinement.
    """
    fake_supervisor_argv = (sys.executable, "-I", "-c", _FAKE_SUPERVISOR_SCRIPT)
    supervisors = link.LiveSupervisors(fake_supervisor_argv)
    supervisor = supervisors.start(("irrelevant",), (("BRIG_TEST_ENV_MARKER", "leaked"),))
    try:
        outcome = supervisors.await_done(supervisor.pid, time.monotonic() + 10.0)
        assert outcome == 0, "the supervisor's own process saw the command's env marker"
    finally:
        supervisors.close(supervisor.pid)
        try:
            os.waitpid(supervisor.pid, 0)
        except ChildProcessError:
            pass


def test_forwarding_term_to_a_supervised_command_still_works_after_the_stdio_fix() -> None:
    """Sanity check alongside the fd 0/1 fix above: `program.py` still forwards
    `SIGTERM` to its one started child and reports its signal-killed exit code,
    unaffected by the child's fd 0/1 no longer being the wire pipes.

    Reads the `started` event itself, directly off `Supervisor`, before sending
    `SIGTERM` -- `_main` installs the forwarding handler right after emitting that
    event -- and waits a further moment past it: synchronizing on the event alone
    still raced the supervisor's own next couple of bytecode instructions closely
    enough to lose occasionally under real scheduling load (measured: this exact
    race lost inside a loaded Docker container, killing the supervisor outright on
    `SIGTERM`'s default disposition before the handler installed, well after it
    had never lost on an otherwise idle host). The extra margin is this test's own
    timing concession, not a property of the fix under test.
    """
    command = (sys.executable, "-I", "-c", "import time; time.sleep(30)")
    supervisors = link.LiveSupervisors(_SUPERVISOR_ARGV)
    supervisor = supervisors.start(command, ())
    try:
        started = supervisor.read_event(time.monotonic() + 10.0)
        assert started is not None and not isinstance(started, link.ReadTimedOut)
        assert wire.done_exit_code(started) is None  # a `started` event, not `done`
        time.sleep(0.2)
        os.kill(supervisor.pid, signal.SIGTERM)
        outcome = supervisors.await_done(supervisor.pid, time.monotonic() + 10.0)
        assert outcome == -signal.SIGTERM
    finally:
        supervisors.close(supervisor.pid)
        try:
            os.waitpid(supervisor.pid, 0)
        except ChildProcessError:
            pass
