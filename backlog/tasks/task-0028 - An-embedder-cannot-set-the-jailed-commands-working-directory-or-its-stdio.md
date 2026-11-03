---
id: TASK-0028
title: An embedder cannot set the jailed command's working directory or its stdio
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T03:26:00Z'
labels:
  - size-3
  - finish-moved
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
- [ ] #2 The fd allow-list the supervisor and its command start with comes from the embedder's Stdio, not a constant in infra or bwrap; Plan.inheritable_fds, which reached no effect, is gone
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal. Criterion #2 restated (finish-moved) before review: as written it asked Plan.inheritable_fds to be what infra applies, but that field reached no effect and the fd policy belongs with the stdio an embedder states, so the field and bwrap's (0, 1, 2) constant are removed and Stdio is the allow-list. Worker's report (Claude): built at d98bc84. create_bwrap_jail(cwd=..., stdio=Stdio(...)); cwd is bwrap's --chdir (domain cwd_refusal: absolute, inside a root, under no mask; PolicyCwdOutsideRoots). Stdio (domain/policy/stdio.py): each of fd 0, 1, 2 a host path or the embedder's own; infra/supervisor/link.py opens them (stdin read-only, stdout and stderr O_APPEND|O_CREAT 0600) and spawns the supervisor with them as fds 0-2 and only the unnamed ones inherited; an open failure is JailSpawnFailed through the driver. tests/e2e/test_cwd_stdio_battery.py: cwd, stdin, stdout, stderr to files (stdout 0600), stderr to /dev/null with stdout the embedder's own (capfd), a cwd outside every root refused; unit cases for --chdir's place and cwd_refusal. uv run just done passes at 993f8bb.
<!-- SECTION:NOTES:END -->
