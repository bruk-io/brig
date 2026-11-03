---
id: TASK-0029
title: >-
  Refuse a policy that does not reach the supervisor's interpreter, before bwrap
  runs
status: To Do
assignee: []
created_date: '2026-11-02T17:23:00Z'
labels:
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. The supervisor runs under the embedder's `sys.executable` (`_supervisor_path`). Measured: a policy that does not bind it (or a link on the way to it, such as a uv-managed Python's `cpython-3.15-<platform>` link) makes bwrap print `execvp ... No such file` on the embedder's stderr and `run_jail` raise `JailExitUnknown: jail process already reaped elsewhere`, which names neither the cause nor the fix. Same shape as `_check_state_dir_reachable`: a pure check over the policy and the interpreter's path and links, raised as a typed error.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 create refuses, before bwrap runs, a policy under which the supervisor's interpreter or a link on the way to it is not reachable, with a typed error naming the path
<!-- AC:END -->
