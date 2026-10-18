"""Shared harness for the brig.py planted-violation tests.

Each test builds a throwaway project under ``tmp_path``, wired to run exactly
one ``pypeeker_rules.brig`` rule, and checks it as a subprocess -- never by
importing pypeeker's engine directly, so the test exercises the same CLI path
``just gates`` does.

The fixture's ``pyproject.toml`` lives at ``tmp_path``'s root, and pypeeker
resolves a plugin name by adding *that* directory to ``sys.path`` before
importing it (confirmed empirically: a plugin module placed beside a
fixture's pyproject.toml loads with no PYTHONPATH set, run from the fixture
root or from a subdirectory of it). So ``plugins = ["pypeeker_rules.brig"]``
only resolves if a real ``pypeeker_rules`` package sits at ``tmp_path``, which
is why this fixture symlinks the repository's one in rather than importing it
directly -- a subprocess in a different cwd cannot see this process's
``sys.path`` either way.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPEEKER = Path(sys.executable).parent / "pypeeker"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def build_fixture(
    tmp_path: Path,
    *,
    rule_id: str,
    src: tuple[str, ...],
    files: dict[str, str],
    rule_config: str = "",
) -> Path:
    """Write ``files`` under ``tmp_path`` and a pyproject.toml enabling only ``rule_id``."""
    (tmp_path / "pypeeker_rules").symlink_to(_REPO_ROOT / "pypeeker_rules")
    for rel_path, content in files.items():
        _write(tmp_path / rel_path, content)
    src_list = ", ".join(f'"{s}"' for s in src)
    config = (
        "[tool.pypeeker]\n"
        f"src = [{src_list}]\n"
        'plugins = ["pypeeker_rules.brig"]\n'
        f'rules = ["{rule_id}"]\n'
        f"{rule_config}"
    )
    _write(tmp_path / "pyproject.toml", config)
    return tmp_path


def run_pypeeker(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_PYPEEKER), *args],
        cwd=project,
        capture_output=True,
        text=True,
    )


def assert_rule_fires(project: Path, rule_id: str, src: tuple[str, ...]) -> None:
    """Index ``src`` under ``project``, run ``check --strict``, and demand ``rule_id`` fired."""
    index = run_pypeeker(project, "index", *src)
    assert index.returncode == 0, index.stdout + index.stderr
    check = run_pypeeker(project, "check", "--strict")
    assert check.returncode != 0, (
        f"expected rule '{rule_id}' to fire; check passed clean:\n{check.stdout}{check.stderr}"
    )
    assert f"[{rule_id}]" in check.stdout, (
        f"rule '{rule_id}' did not appear in check output:\n{check.stdout}{check.stderr}"
    )


def assert_rule_clean(project: Path, rule_id: str, src: tuple[str, ...]) -> None:
    """Index ``src`` under ``project`` and demand ``check --strict`` reports no ``rule_id`` finding.

    For a negative case: code the rule must *not* flag. Still asserts the
    index step itself succeeded, so a typo in the planted fixture fails loud
    rather than passing by accident.
    """
    index = run_pypeeker(project, "index", *src)
    assert index.returncode == 0, index.stdout + index.stderr
    check = run_pypeeker(project, "check", "--strict")
    assert f"[{rule_id}]" not in check.stdout, (
        f"rule '{rule_id}' fired on code it should accept:\n{check.stdout}{check.stderr}"
    )
