"""E2E tests for `infra/proxy/assemble.py` (TASK-0001.36, decision-0009 item 2): the egress
proxy's one file is the egress decision's source, the log envelope's (`infra/log.py`,
TASK-0001.37) and `program.py`'s, exactly, standard library only, and it refuses an interpreter
older than brig's floor by name. A gateway test of one infra module (decision-0001 rule 4): the
decision's source is read from its path beside the installed package, never imported here."""

import ast
import base64
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from brig.infra.proxy import assemble

_PROGRAM = Path(assemble.__file__).with_name("program.py")
_DECISION = Path(assemble.__file__).parents[2] / "domain" / "policy" / "egress.py"
_LOG = Path(assemble.__file__).parents[1] / "log.py"


def _blobs(assembled: str) -> list[str]:
    return [
        base64.b64decode(node.args[0].value).decode("utf-8")
        for node in ast.walk(ast.parse(assembled))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "b64decode"
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, bytes)
    ]


def test_the_assembled_file_is_exactly_the_decision_the_envelope_then_the_program() -> None:
    decision = _DECISION.read_text(encoding="utf-8")

    assert _blobs(assemble.assembled_source(decision)) == [
        decision,
        _LOG.read_text(encoding="utf-8"),
        _PROGRAM.read_text(encoding="utf-8"),
    ]


def test_the_assembled_sources_import_nothing_outside_the_standard_library() -> None:
    roots: set[str] = set()
    for path in (_DECISION, _LOG, _PROGRAM):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                assert node.level == 0, f"{path} has a relative import"
                roots.add(node.module.split(".")[0])

    assert {"socket", "ipaddress"} <= roots
    assert roots <= sys.stdlib_module_names, roots - sys.stdlib_module_names


def _older_interpreter() -> str | None:
    for name in ("python3", "python3.13", "python3.12", "python3.11", "python3.10"):
        found = shutil.which(name)
        if found is None:
            continue
        version = subprocess.run(
            [found, "-c", "import sys; print(*sys.version_info[:3])"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        if version and tuple(int(part) for part in version) < (3, 15):
            return found
    return None


def test_the_assembled_file_refuses_an_older_interpreter_from_its_stdin() -> None:
    """Run as the proxy is run, its program on its stdin (`-I -`), by a real older Python."""
    older = _older_interpreter()
    if older is None:
        pytest.skip("no Python older than 3.15 on this host")
    installed = subprocess.run(
        [older, "-c", "import sys; print(*sys.version_info[:3])"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    done = subprocess.run(
        [older, "-I", "-"],
        input=assemble.assembled_source(_DECISION.read_text(encoding="utf-8")),
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.returncode == 1
    assert done.stderr == (
        "brig's egress proxy requires Python 3.15 or later; this interpreter is "
        + ".".join(installed)
        + "\n"
    )
