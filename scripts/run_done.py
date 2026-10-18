#!/usr/bin/env python3
"""The step runner `just done` calls.

Every tool invocation lives in exactly one justfile recipe; this script only
orchestrates calling them, collects every failure instead of stopping at the
first, and reports pass/fail per step plus a one-line summary. A test layer
with nothing collected yet (no e2e tests on this skeleton) is reported as
such, never silently skipped and never counted as a failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PYTEST_NO_TESTS_COLLECTED = 5


def just(*recipe: str) -> tuple[int, str]:
    proc = subprocess.run(["just", *recipe], cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def just_test_layer(layer: str) -> tuple[int, str]:
    code, output = just(f"test-{layer}")
    if code == PYTEST_NO_TESTS_COLLECTED:
        return 0, f"no {layer} tests yet\n"
    return code, output


def main() -> int:
    steps: list[tuple[str, tuple[int, str]]] = [
        ("lint", just("lint")),
        ("typecheck", just("typecheck")),
        ("gates", just("gates")),
        ("pypeeker rule tests", just("test-pypeeker-rules")),
        ("unit tests", just_test_layer("unit")),
        ("integration tests (pass 1)", just_test_layer("integration")),
        ("integration tests (pass 2)", just_test_layer("integration")),
        ("e2e tests", just_test_layer("e2e")),
        ("docs build", just("docs")),
        ("architecture validate", just("arch-validate")),
        ("architecture lint", just("arch-lint")),
    ]

    failed: list[str] = []
    for name, (code, output) in steps:
        status = "PASS" if code == 0 else "FAIL"
        print(f"== {name}: {status} ==")
        if output.strip():
            print(output.rstrip())
        if code != 0:
            failed.append(name)
        print()

    if failed:
        print(f"done: {len(failed)} step(s) failed: {', '.join(failed)}")
        return 1
    print("done: all steps passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
