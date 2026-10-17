---
id: DRAFT-0004
title: >-
  Confirm bwrap's --unshare-all works unprivileged on GitHub's ubuntu-latest
  runner
status: Draft
assignee: []
created_date: '2026-10-17 21:53'
labels:
  - brig
  - ci
dependencies: []
documentation:
  - .github/workflows/ci.yml
parent_task_id: TASK-0001
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

TASK-0001.03's adversarial review raised an open question about its own e2e test (`tests/e2e/test_bwrap_journey.py`) that could not be settled on a macOS development host (no bwrap, no Docker daemon, no Linux VM): bwrap's `--unshare-all` needs unprivileged user namespaces, and Ubuntu 24.04 ships an AppArmor profile that restricts them by default (`kernel.apparmor_restrict_unprivileged_userns_clone`-style confinement) -- a change that broke a number of CI pipelines when 24.04 became `ubuntu-latest` on GitHub-hosted runners in 2024.

`.github/workflows/ci.yml` installs bubblewrap on `ubuntu-latest` and runs `just done` with no special AppArmor/sysctl step. Whether the walking skeleton's e2e test (and every later bwrap e2e test) actually passes on its first real CI run, rather than failing with a permissions error on `--unshare-all` unrelated to anything brig's own code does, depends entirely on whether GitHub's runner image already relaxed that restriction (their `runner-images` project is known to have patched exactly this for several popular sandboxing tools) or whether the workflow needs an explicit step.

## What finishes this

- [ ] Push this repository (or a throwaway branch) so CI actually runs once, and read whether `tests/e2e/test_bwrap_journey.py` passes or fails on `--unshare-all` specifically.
- [ ] If it fails for that reason, decide and add the minimal CI fix (e.g. `sudo sysctl kernel.apparmor_restrict_unprivileged_userns=0`, or an AppArmor profile permitting bwrap) to `.github/workflows/ci.yml`.
- [ ] If it passes, note that here so nobody re-opens this question.

## Notes

Nothing has been pushed to a real git remote yet as of TASK-0001.03 (explicitly out of scope for that task -- a separate decision for the repo owner), so this is genuinely unverified, not just unverified-by-TASK-0001.03.
<!-- SECTION:DESCRIPTION:END -->
