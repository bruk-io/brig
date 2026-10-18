---
id: TASK-0016
title: >-
  infra.processes._group_alive_proc_scan can raise IndexError/ValueError out of
  group_alive, past the driver's deliberately-unwrapped Verify arm
status: To Do
assignee: []
created_date: '2026-10-18 20:04'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0013's new Linux /proc scan parses each /proc/<pid>/stat by `stat_line.rpartition(")")` and then reads `fields[0]`/`fields[2]` and `int(candidate_pgid)`. Two expressions there are narrower than infra's own stated contract (decision-0001 rules 1 and 9: infra hands back plain data and never raises):

- `state, candidate_pgid = fields[0], fields[2]` raises IndexError if the stat read comes back empty or truncated (`"".rpartition(")")` -> `("", "", "")` -> `fields == []`).
- `int(candidate_pgid)` raises ValueError on a line with no `)` at all.

The per-entry `except FileNotFoundError, ProcessLookupError, PermissionError` covers the open/read, not the parse; `group_alive`'s own outer `except FileNotFoundError` only covers the no-/proc (macOS) fallback. Either exception escapes `group_alive` as a raw stdlib exception, through `presentation/drivers/bwrap.py`'s `Verify` arm -- which deliberately does not wrap its port calls, on the documented claim that `group_alive` returns a bool rather than raising -- and crosses the public API as a non-brig exception (decision-0001 rule 13). That is the exact shape .claude/rules/driver-exception-boundary.md records escaping twice before.

Not blocking TASK-0013: no instance has been measured, and bwrap.py's own docstring sets the bar at 'should any of them ever be measured raising'. Reviewer's measurements found the scan correct in every case exercised (brig-probe-amd64:latest, 2026-10-18). Filed so the parse is hardened before something measures it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 _group_alive_proc_scan tolerates a malformed or truncated /proc/<pid>/stat line the same way it already tolerates a vanished one -- skip that entry, never fail the scan
- [ ] #2 group_alive is shown by test to return a bool (never raise) for a /proc entry whose stat line is empty or has no ')'
<!-- AC:END -->
