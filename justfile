# brig: the project's one entry point. Every command line lives here, once.

set shell := ["bash", "-euo", "pipefail", "-c"]

# list every recipe
default:
    @just --list

# ruff: lint and format, both checked
lint:
    uv run ruff check .
    uv run ruff format --check .

# mypy strict
typecheck:
    uv run mypy

# index the project, then run every pypeeker rule strict
gates:
    uv run pypeeker index src tests pypeeker_rules
    uv run pypeeker check --strict

# run an explicit set of test paths (used by `check` and the layer recipes)
test-selected *paths:
    uv run pytest {{paths}} -rs

# tests/unit: one pure function each, nothing mocked
test-unit:
    @just test-selected tests/unit

# tests/integration: brig's own parts together, the world faked at its edge
test-integration:
    @just test-selected tests/integration

# tests/e2e: the real world, nothing faked
test-e2e:
    @just test-selected tests/e2e

# pypeeker_rules/tests: meta-tests of brig's own custom pypeeker rules in
# pypeeker_rules/brig.py -- not one of decision-0001's three test layers, so
# it is run on its own rather than folded into test-unit/-integration/-e2e
test-pypeeker-rules:
    @just test-selected pypeeker_rules/tests

# mkdocs, failing on any warning
docs:
    uv run mkdocs build --strict

# LikeC4's own validation of the architecture model
arch-validate:
    npx -y likec4@1.60.0 validate docs/architecture

# the c4-architecture plugin's orthodox-C4 rules, beyond what LikeC4 itself enforces
arch-lint:
    uv run python3 scripts/c4lint.py docs/architecture

# only the unit and integration tests the change reaches (diff against main, plus uncommitted/untracked)
check:
    #!/usr/bin/env bash
    set -euo pipefail
    files=$(uv run python3 scripts/affected_tests.py)
    if [ -z "$files" ]; then
        echo "check: nothing reached by the change"
    else
        just test-selected $files || test "$?" -eq 5
    fi

# everything: ruff, mypy, pypeeker, the pypeeker rule tests, every test layer
# (integration twice), docs, architecture lint
done:
    uv run python3 scripts/run_done.py
