---
id: DRAFT-0016
title: An embedder cannot set the jailed command's working directory or its stdio
status: Draft
assignee: []
created_date: '2026-11-02T17:23:00Z'
labels:
  - size-3
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. Measured: the command starts in the embedder's own working directory (there is no `--chdir`), and its stdout and stderr come out on the embedder's own fds (`_INHERITABLE_FDS = (0, 1, 2)`, and `infra/supervisor/link.py` hands the supervisor the embedder's 0/1/2). An embedder that runs several jails in different directories cannot chdir its own process to suit each, and one that owns its terminal (a TUI) has a jailed traceback painted over it. `Plan.inheritable_fds` reaches no effect, so the fd policy sits hard-coded in infra.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 create takes a working directory for the command, and an stdio policy (at least: stdout and stderr to a file brig returns, or to nothing)
- [ ] #2 Plan.inheritable_fds is what infra applies, not a constant in infra
<!-- AC:END -->
