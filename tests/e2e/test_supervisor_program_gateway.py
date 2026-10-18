"""E2E gateway test for `infra/supervisor/program.py` (TASK-0001.15 step 5).

Decision-0001 rule 4 lets an e2e test import one `brig.infra` module directly, for
exactly this: running `infra/supervisor/program.py` -- the file dropped as PID 1
inside a real jail's namespace (decision-0002) -- as a real subprocess, speaking its
real wire protocol over real pipes, with no bwrap and no namespace involved. That is
the whole of what this file calls "the reap-everything-as-PID-1 loop": the part of
`program.py` that needs no jail to exercise, because it is just process-management
logic against whatever children it actually has (`_main`'s own
read-start-reap-report journey) -- not the namespace-dependent half, where a
grandchild actually reparents to this process *because* it is PID 1 of a real
namespace. That half needs a real PID namespace to produce at all (outside one, a
process this test spawns directly is not a subreaper, so a grandchild its own child
leaves behind reparents to the host's own init, never to this test) --
`tests/e2e/test_supervisor_reaps_orphans.py` covers it for real, skip-guarded on
bwrap.

TASK-0001.15's own plan named this a "unit test... drive program.py's reap loop by
hand". Settled empirically here, not by further argument, that it cannot be one:
`program.py` is `brig.infra`, and decision-0001 rule 4's own gate
(`brig-test-layers`) refuses `tests/unit/` importing anything outside `brig.domain`
-- confirmed by running `pypeeker check --strict` against a throwaway probe import,
the same way DRAFT-0009's own sharing question was settled by trying it rather than
guessing. `under-exposed-access` separately refuses reaching into another module's
own `_name`s from a test exactly as it would from production code, which blocks
calling `program._reap_until_gone`/`_start_child` directly from any layer, not only
`tests/unit/`. Driving the real file as a subprocess, over its own public wire
protocol (`wire.encode_exec_request`/`wire.decode_event`, both public names with a
real caller already -- `link.py`'s own) is this module's actual seam; nothing here
reaches into `program.py`'s own `_name`s, mirroring `test_processes_gateway.py`'s
house precedent for a gateway test of one infra module with nothing mocked.

Every supervised command below writes nothing to its own stdout, though that is no
longer the reason it must not: DRAFT-0010's resolution moved the wire protocol
itself off fd 0/1/2 entirely, onto `wire.REQUEST_FD`/`wire.EVENTS_FD` (3/4) --
`_run_supervised` below wires those two, mirroring (not importing)
`infra/supervisor/link.py`'s own fd-placement technique, the same reason this
file's own module docstring already gives for not going through `link.py` at
all. `argv`'s own fd 0/1/2 are left to this subprocess's ordinary inherited
streams, exactly as `program.py`'s `_start_child` leaves them for the real
command it starts -- a write to stdout here would land on this test's own
stdout, same as any ordinary subprocess, and would not reach (or be reachable
from) this file's own event stream either way. `true`, a shell that only ever
calls `exit`, and a process that only signals itself were chosen for the
simplicity of having nothing to say on stdout at all regardless --
`test_supervisor_link_gateway.py`'s own forged-`done` test is precisely a
command that writes to its own stdout, to prove that write cannot reach the
event stream any more (TASK-0001.15/.17 adversarial review's own finding,
`program.py`'s `_start_child` explicitly closing `wire.REQUEST_FD`/
`wire.EVENTS_FD` for the real command it starts, regardless of what its own
fd 0/1/2 do).
"""

import os
import sys
from typing import cast

from brig.infra.supervisor import program, wire

_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
"""The one environment `program.py`'s own exec request carries below: just enough
`PATH` for `os.posix_spawnp` to find `true`/`sh` by name. Every other test in this
suite that reaches `program.py` through the public API runs the supervised command
with no environment at all (`domain/plan.py`'s own "known gap", until
TASK-0001.17's allow-list policy exists); this file is not testing that policy, so
it hands `program.py` an environment of its own rather than inherit that gap.
"""


def _spawn_program_with_wire_fds(request_read_fd: int, events_write_fd: int) -> int:
    """Start `infra/supervisor/program.py` as a real subprocess with its own fd
    `wire.REQUEST_FD`/`wire.EVENTS_FD` connected to `request_read_fd`/
    `events_write_fd` (this process's own fds), and return its pid.

    Mirrors, rather than imports, `infra/supervisor/link.py`'s own fd-placement
    technique (this file's own module docstring already explains why it does not
    import that module at all): every source fd that collides with either target
    -- its own included, since `os.posix_spawn`'s `DUP2` file action is specified
    to do nothing at all, not even clear the close-on-exec flag a freshly-opened
    pipe fd carries by default (PEP 446), when a source and its target are the
    same number -- is first duplicated onto an uncontested number before the real
    `DUP2` action runs, so this is correct regardless of this test process's own
    fd allocation state, exactly the same hazard `infra/processes.py`'s own
    `_resolve_fd_sources` exists to answer for `link.py`'s real spawn.
    """
    sources = {wire.REQUEST_FD: request_read_fd, wire.EVENTS_FD: events_write_fd}
    targets = frozenset(sources)
    resolved: dict[int, int] = {}
    relocated: list[int] = []
    for target, source in sources.items():
        if source in targets:
            new_source = os.dup(source)
            relocated.append(new_source)
            resolved[target] = new_source
        else:
            resolved[target] = source
    file_actions: list[tuple[int, ...]] = [
        (os.POSIX_SPAWN_DUP2, source, target) for target, source in resolved.items()
    ]
    file_actions += [(os.POSIX_SPAWN_CLOSE, source) for source in resolved.values()]
    try:
        return os.posix_spawnp(
            sys.executable,
            [sys.executable, program.__file__],
            dict(os.environ),
            file_actions=file_actions,
        )
    finally:
        for fd in relocated:
            os.close(fd)


def _run_supervised(argv: tuple[str, ...]) -> tuple[list[dict[str, object]], int]:
    """Run `infra/supervisor/program.py` as a real subprocess with `argv` as the one
    command it supervises, and return every event it reports plus its own exit code.

    Speaks the wire protocol directly, the same shape `infra/supervisor/link.py`'s
    `_start`/`Supervisor` do from inside brig -- deliberately not through `link.py`
    itself, so nothing here depends on that module's own correctness; the two are
    not the same code, and this file is not an integration test of their pairing.

    Returns each event as a plain `dict[str, object]`, not `wire.Event`: that union
    has no `Literal`-typed `kind` field to narrow it on (`wire.py`'s own
    `done_exit_code` is the one sanctioned way outside `wire.py` to tell its three
    shapes apart, and it only answers "is this `done`"), so indexing a `started` or
    `exited` event's own `pid`/`exit_code` field on the union type itself fails
    mypy strict's TypedDict-item check -- `_StartedEvent`/`_ExitedEvent`/
    `_DoneEvent` are themselves private, so casting to one of those by name from
    here would trade a `brig-test-layers` problem for an `under-exposed-access` one.
    Erasing to a plain dict at this one boundary, right where `wire.decode_event`'s
    real return value is read, keeps every event's real shape (nothing here invents
    a field `wire.py` did not actually send) while letting the tests below index it
    like the ordinary JSON object it is on the wire.
    """
    request_read_fd, request_write_fd = os.pipe()
    events_read_fd, events_write_fd = os.pipe()
    pid = _spawn_program_with_wire_fds(request_read_fd, events_write_fd)
    os.close(request_read_fd)
    os.close(events_write_fd)
    with os.fdopen(request_write_fd, "w") as request_pipe:
        request_pipe.write(wire.encode_exec_request(argv, _ENV))
    events: list[dict[str, object]] = []
    with os.fdopen(events_read_fd, "r") as events_pipe:
        for line in events_pipe:
            events.append(cast(dict[str, object], wire.decode_event(line)))
    _, status = os.waitpid(pid, 0)
    returncode = os.waitstatus_to_exitcode(status)
    return events, returncode


def test_program_reaps_a_normally_exiting_child_and_reports_its_exit_code() -> None:
    """The happy path: `started`, then `exited` with the child's own real exit code
    (0), then `done` carrying the same code -- `program.py`'s whole journey for a
    command that exits cleanly on its own, with the supervisor process itself then
    exiting 0 too.
    """
    events, supervisor_exit = _run_supervised(("true",))

    assert len(events) == 3
    started, exited, done = events
    assert started["kind"] == "started"
    assert isinstance(started["pid"], int) and started["pid"] > 0
    assert exited == {"kind": "exited", "pid": started["pid"], "exit_code": 0}
    assert done == {"kind": "done", "exit_code": 0}
    assert supervisor_exit == 0


def test_program_carries_a_nonzero_exit_code_through_unchanged() -> None:
    """A command that calls `exit` with a non-zero code on its own has that exact
    code carried through both `exited` and `done`, not collapsed into a generic
    failure.
    """
    events, supervisor_exit = _run_supervised(("sh", "-c", "exit 7"))

    assert len(events) == 3
    started, exited, done = events
    assert exited == {"kind": "exited", "pid": started["pid"], "exit_code": 7}
    assert done == {"kind": "done", "exit_code": 7}
    assert supervisor_exit == 0


def test_program_reports_a_signal_killed_childs_negative_exit_code() -> None:
    """A command a signal kills, rather than one that calls `exit` itself, reports
    the negative of that signal's own number through both events --
    `os.waitstatus_to_exitcode`'s own convention (`infra/processes.py`'s `reap`
    carries the same one; `program.py` duplicates the mechanism, this file's own
    module docstring already explains why, not the convention, since both call the
    same stdlib function).
    """
    self_term = (
        sys.executable,
        "-c",
        "import os, signal; os.kill(os.getpid(), signal.SIGTERM)",
    )
    events, supervisor_exit = _run_supervised(self_term)

    assert len(events) == 3
    started, exited, done = events
    assert exited == {"kind": "exited", "pid": started["pid"], "exit_code": -15}
    assert done == {"kind": "done", "exit_code": -15}
    assert supervisor_exit == 0
