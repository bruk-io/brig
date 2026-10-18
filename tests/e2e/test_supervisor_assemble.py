"""E2E tests for `infra/supervisor/assemble.py` (TASK-0001.15 AC#1's remaining-work
addendum): the one file decision-0001 rule 17 requires -- `wire.py` + `program.py`,
assembled, stdlib only, refusing an interpreter older than this project's own floor.

Decision-0001 rule 4 lets an e2e test import a `brig.infra` module directly, the same
allowance `test_supervisor_program_gateway.py` already uses for `program.py` itself --
`assemble.py` is `brig.infra.supervisor`, so this file's tests live here for the same
reason, not because anything below needs a real jail or a real bwrap.
"""

import ast
import base64
import io
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import cast

import pytest

from brig.infra.supervisor import assemble, program, wire

_OLDER_PYTHON_CANDIDATES = (
    "python3.9",
    "python3.10",
    "python3.11",
    "python3.12",
    "python3.13",
    "python3.14",
)
"""Every Python 3 minor version older than this project's own floor (3.15,
`pyproject.toml`'s `requires-python`) that might plausibly be installed on a
developer's host under its own name -- the same measured, not assumed, way
every other platform-dependent battery in this suite looks for what it
needs (`shutil.which`), rather than assuming a fixed version is present.
"""


def _find_older_python() -> str | None:
    """The path to the first interpreter among `_OLDER_PYTHON_CANDIDATES` this
    host actually has installed, or `None` if none of them are.
    """
    for candidate in _OLDER_PYTHON_CANDIDATES:
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


def test_assembled_source_is_exactly_wire_then_program_source() -> None:
    """The base64 blob `assembled_source` builds, decoded back out, is exactly
    `wire.py`'s current source plus `program.py`'s current source -- so this
    fails the moment either file changes without re-assembling, never a second
    checked-in artifact that can go stale on its own.
    """
    assembled = assemble.assembled_source()
    tree = ast.parse(assembled)
    call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "b64decode"
    )
    (blob_node,) = call.args
    assert isinstance(blob_node, ast.Constant)
    assert isinstance(blob_node.value, bytes)

    decoded = base64.b64decode(blob_node.value).decode("utf-8")
    wire_source = Path(wire.__file__).read_text(encoding="utf-8")
    program_source = Path(program.__file__).read_text(encoding="utf-8")
    assert decoded == wire_source + program_source


def test_assembled_source_imports_nothing_outside_the_stdlib() -> None:
    """Every `import`/`from ... import` the assembled body contains (`wire.py`'s
    own plus `program.py`'s own, since the preamble above them imports only
    `sys`/`base64`, already stdlib) names a module this interpreter's own
    stdlib provides -- rule 17's "stdlib only" for the one thing that matters
    once this file is dropped as PID 1 inside a jail with no `brig` package
    installed around it to resolve anything else against.
    """
    wire_source = Path(wire.__file__).read_text(encoding="utf-8")
    program_source = Path(program.__file__).read_text(encoding="utf-8")
    tree = ast.parse(wire_source + program_source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            roots.add(node.module.split(".")[0])

    assert roots, "expected at least one import to confirm this check inspects anything at all"
    stdlib = sys.stdlib_module_names
    assert roots <= stdlib, f"non-stdlib import(s) found: {roots - stdlib}"


def test_refusal_message_mentions_the_required_version_for_an_old_interpreter() -> None:
    """`refusal_message` is pure and callable with a synthetic version tuple --
    no real old interpreter needed to confirm what it would have said.
    """
    message = assemble.refusal_message((3, 9, 0))
    assert "3.15" in message
    assert "3.9.0" in message


def test_preamble_message_agrees_with_refusal_message_for_the_same_version() -> None:
    """The assembled file's own preamble -- extracted and executed here with a
    synthetic `sys.version_info`, never a real old interpreter -- writes to
    stderr exactly what `refusal_message` returns for the same installed
    version, and exits non-zero. Confirms the two cannot read differently for
    the same version, the one thing `assembled_source`'s own docstring claims
    about `_preamble`'s embedded duplicate.
    """
    preamble_source = _preamble_guard_body()
    fake_sys = types.SimpleNamespace(version_info=(3, 9, 0), stderr=io.StringIO())

    def fake_exit(code: int) -> None:
        raise SystemExit(code)

    fake_sys.exit = fake_exit
    namespace: dict[str, object] = {"sys": fake_sys}

    with pytest.raises(SystemExit) as excinfo:
        exec(compile(preamble_source, "<preamble>", "exec"), namespace)

    assert excinfo.value.code == 1
    assert fake_sys.stderr.getvalue() == assemble.refusal_message((3, 9, 0)) + "\n"


def test_preamble_does_not_fire_for_an_interpreter_that_clears_the_floor() -> None:
    """The same preamble, run with a `sys.version_info` that already clears
    rule 17's floor, writes nothing and does not exit -- the guard is a
    refusal, not an unconditional message.
    """
    preamble_source = _preamble_guard_body()
    fake_sys = types.SimpleNamespace(version_info=(3, 15, 0), stderr=io.StringIO())
    namespace: dict[str, object] = {"sys": fake_sys}

    exec(compile(preamble_source, "<preamble>", "exec"), namespace)

    assert fake_sys.stderr.getvalue() == ""


def test_real_assembled_file_runs_the_supervisor_journey_under_this_interpreter() -> None:
    """The real assembled file, written to disk and run as a real subprocess
    under this host's own (>=3.15) interpreter, speaks the wire protocol and
    supervises a real command exactly as `program.py` does directly
    (`test_supervisor_program_gateway.py`'s own journey) -- confirming the
    assembled artifact itself, not only its two source files individually,
    actually works end to end as the supervisor.
    """
    assembled_path = _write_assembled_file()
    try:
        events, supervisor_exit = _run_assembled_supervised(assembled_path, ("true",))
    finally:
        os.unlink(assembled_path)

    assert len(events) == 3
    started, exited, done = events
    assert started["kind"] == "started"
    assert isinstance(started["pid"], int) and started["pid"] > 0
    assert exited == {"kind": "exited", "pid": started["pid"], "exit_code": 0}
    assert done == {"kind": "done", "exit_code": 0}
    assert supervisor_exit == 0


@pytest.mark.skipif(
    _find_older_python() is None,
    reason=(
        "no Python 3 interpreter older than this project's own floor (3.15) was "
        f"found among {_OLDER_PYTHON_CANDIDATES} on this host"
    ),
)
def test_real_assembled_file_refuses_a_real_older_interpreter() -> None:
    """The real assembled file, run as a real subprocess under whatever older
    Python 3 interpreter this host actually has installed, exits non-zero and
    prints a message naming the version it needs -- a refusal, not a bare
    traceback -- confirming rule 17's "refuses an older interpreter, saying
    which it needs" for real, not only through the synthetic-`sys.version_info`
    check above.
    """
    older_python = _find_older_python()
    assert older_python is not None  # narrowed by the skipif above

    assembled_path = _write_assembled_file()
    try:
        result = subprocess.run(
            [older_python, assembled_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        os.unlink(assembled_path)

    assert result.returncode != 0
    assert "3.15" in result.stderr
    assert "Traceback" not in result.stderr


def _preamble_guard_body() -> str:
    """The assembled file's preamble, minus its own leading `import sys`: the
    two tests above inject a fake `sys` (a `types.SimpleNamespace` with a
    synthetic `version_info`) into the `exec` namespace they run this in, and
    a real `import sys` statement in that same namespace would rebind `sys`
    right back to the real module, defeating the whole point of faking it.
    `_preamble`'s own guard logic is everything after that first line.
    """
    preamble_source, _, _ = assemble.assembled_source().partition("import base64\n")
    _, _, guard_body = preamble_source.partition("\n")
    return guard_body


def _write_assembled_file() -> str:
    """Write the real `assembled_source()` to a fresh temporary file and
    return its path -- mirroring, on a smaller scale, what `presentation/
    api.py`'s own `_supervisor_path` does for a real jail.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="brig-supervisor-test-", delete=False
    ) as handle:
        handle.write(assemble.assembled_source())
        return handle.name


def _run_assembled_supervised(
    assembled_path: str, argv: tuple[str, ...]
) -> tuple[list[dict[str, object]], int]:
    """Run the assembled file at `assembled_path` as a real subprocess with
    `argv` as the one command it supervises, and return every event it
    reports plus its own exit code.

    Mirrors `test_supervisor_program_gateway.py`'s own `_spawn_program_with_
    wire_fds`/`_run_supervised` exactly, pointed at the assembled file instead
    of `program.py` directly -- the one difference that matters here, since
    this file's whole point is confirming the assembled artifact, not
    `program.py` alone, behaves the same way.
    """
    request_read_fd, request_write_fd = os.pipe()
    events_read_fd, events_write_fd = os.pipe()
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
        pid = os.posix_spawnp(
            sys.executable,
            [sys.executable, "-I", assembled_path],
            dict(os.environ),
            file_actions=file_actions,
        )
    finally:
        for fd in relocated:
            os.close(fd)
    os.close(request_read_fd)
    os.close(events_write_fd)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    with os.fdopen(request_write_fd, "w") as request_pipe:
        request_pipe.write(wire.encode_exec_request(argv, env))
    events: list[dict[str, object]] = []
    with os.fdopen(events_read_fd, "r") as events_pipe:
        for line in events_pipe:
            events.append(cast(dict[str, object], wire.decode_event(line)))
    _, status = os.waitpid(pid, 0)
    returncode = os.waitstatus_to_exitcode(status)
    return events, returncode
