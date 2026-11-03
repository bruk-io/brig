---
id: TASK-0029
title: >-
  Refuse a policy that does not reach the supervisor's interpreter, before bwrap
  runs
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T03:43:00Z'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03. Worker's report (Claude): built at 55336cd. infra.files.link_chain(path) lists every path a lookup passes through (the path, then the path with each link on the way replaced by its target, until none is; 40 links at most, as the kernel). domain interpreter_refusal requires each to be inside a root of the policy and under no mask (a mount shows a link's target only where the link is mounted too); create_bwrap_jail checks sys.executable's chain before writing anything and raises PolicyInterpreterUnreachable naming the first path missed. e2e: a system-tree-only policy is refused naming sys.executable (skips where the interpreter lives under the system tree); unit cases for a venv -> version-manager link -> install chain, mounted, half-mounted and masked. uv run just done passes.
<!-- SECTION:NOTES:END -->
