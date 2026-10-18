#!/usr/bin/env python3
"""Select the unit and integration tests a change reaches.

`just check` runs only these: the tests that transitively import a file
differing from `main`, plus every uncommitted or untracked file, plus any
changed test file itself. Prints one relative path per line.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_LAYER_ROOTS = (ROOT / "tests" / "unit", ROOT / "tests" / "integration")


def changed_files() -> set[Path]:
    """Files differing from `main`, plus every uncommitted or untracked file."""
    diff = subprocess.run(
        ["git", "diff", "--name-only", "main...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    paths = set(diff) | {line[3:] for line in status if len(line) > 3}
    files: set[Path] = set()
    for p in paths:
        if not p:
            continue
        full = ROOT / p
        if full.is_dir():
            files.update(full.rglob("*.py"))
        else:
            files.add(full)
    return files


def discover_modules(root: Path, dotted_prefix: tuple[str, ...]) -> dict[str, Path]:
    """Map a dotted module name to its file, for every `.py` file under root."""
    modules: dict[str, Path] = {}
    if not root.is_dir():
        return modules
    for path in sorted(root.rglob("*.py")):
        rel_parts = list(path.relative_to(root).parts)
        if rel_parts[-1] == "__init__.py":
            rel_parts = rel_parts[:-1]
        else:
            rel_parts[-1] = rel_parts[-1].removesuffix(".py")
        modules[".".join((*dotted_prefix, *rel_parts))] = path
    return modules


def imported_modules(path: Path, known: dict[str, Path]) -> set[str]:
    """The modules under `known` that `path` imports, directly."""
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError, OSError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    resolved: set[str] = set()
    for name in names:
        parts = name.split(".")
        while parts:
            candidate = ".".join(parts)
            if candidate in known:
                resolved.add(candidate)
                break
            parts = parts[:-1]
    return resolved


def reached_tests(changed: set[Path]) -> set[Path]:
    """Every unit/integration test that transitively reaches a changed file."""
    src_modules = discover_modules(ROOT / "src", ())
    test_modules = discover_modules(ROOT / "tests", ("tests",))
    known = {**src_modules, **test_modules}
    path_to_module = {path: name for name, path in known.items()}

    importers_of: dict[str, set[str]] = {name: set() for name in known}
    for name, path in known.items():
        for dep in imported_modules(path, known):
            importers_of[dep].add(name)

    selected: set[str] = set()
    for changed_path in changed:
        start = path_to_module.get(changed_path)
        if start is None:
            continue
        stack, seen = [start], {start}
        while stack:
            current = stack.pop()
            for importer in importers_of.get(current, ()):
                if importer not in seen:
                    seen.add(importer)
                    stack.append(importer)
        selected |= seen

    def is_test_file(path: Path) -> bool:
        return path.name.startswith("test_") and any(
            root in path.parents for root in TEST_LAYER_ROOTS
        )

    result = {known[name] for name in selected if is_test_file(known[name])}
    result |= {p for p in changed if is_test_file(p)}
    return result


def main() -> int:
    for path in sorted(reached_tests(changed_files())):
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
