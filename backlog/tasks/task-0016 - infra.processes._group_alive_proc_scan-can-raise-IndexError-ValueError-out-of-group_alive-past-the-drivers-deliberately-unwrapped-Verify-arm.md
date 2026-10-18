---
id: TASK-0016
title: >-
  infra.processes._group_alive_proc_scan can raise IndexError/ValueError out of
  group_alive, past the driver's deliberately-unwrapped Verify arm
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 20:04'
updated_date: '2026-10-18 22:18'
labels:
  - brig
  - size-1
dependencies: []
modified_files:
  - src/brig/infra/processes.py
  - tests/e2e/test_processes_gateway.py
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
- [x] #1 _group_alive_proc_scan tolerates a malformed or truncated /proc/<pid>/stat line the same way it already tolerates a vanished one -- skip that entry, never fail the scan
- [x] #2 group_alive is shown by test to return a bool (never raise) for a /proc entry whose stat line is empty or has no ')'
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Wrap `_group_alive_proc_scan`'s parse of a successfully-opened `/proc/<pid>/stat`
   line (rest.split(), fields[0]/fields[2], int(candidate_pgid)) in the same
   per-entry tolerance the open/read already has: a malformed or truncated line
   (empty after rpartition, fewer than 3 fields, a pgid field that isn't an int)
   skips that one entry, never fails the whole scan -- (IndexError, ValueError),
   same `continue` as the existing except clause.
2. Test: force the exact shapes (empty stat content, a line with no ')' at all,
   a line with too few fields after the split) and confirm `group_alive` still
   returns a plain bool, never raises, the same way it already tolerates a
   vanished `/proc` entry.

### Proof
- just gates, just typecheck, just done green.
- The new test fails against the pre-fix code for the right reason (IndexError/
  ValueError escaping), then passes against the fix.

### Risks
- Low: the fix only widens what's already-tolerated per-entry; verify it doesn't
  accidentally swallow something that SHOULD still cause the scan to report
  correctly for a genuinely-alive, well-formed entry elsewhere in /proc.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Implementation notes (2026-10-18)

Fixed per the committed plan: `_group_alive_proc_scan`'s parse of a successfully-opened
`/proc/<pid>/stat` line now catches `(IndexError, ValueError)` around
`fields[0]`/`fields[2]`/`int(candidate_pgid)` and `continue`s to the next entry, the same
tolerance the existing open/read `except` already had.

One deviation from the plan's literal text, forced by `just gates`: the plan didn't say
how the test would reach the malformed shapes without faking `/proc` (decision-0001 rule
5 bars patches everywhere, and the e2e rule runs against the real thing). The real kernel
never writes a malformed stat line, so proving the tolerance needs a real but *fabricated*
`/proc`-shaped directory. Tried calling `_group_alive_proc_scan` directly from the test
(rule 4 allows a gateway test to import one `brig.infra` module) -- pypeeker's
`under-exposed-access` rule rejected it (protected name accessed from `tests`). Fallback:
added the same `proc_root: str = "/proc"` parameter to the public `group_alive` too,
defaulting to the real `/proc` for every production caller, so the test can call the
public function directly instead of reaching into the private one.

Three new tests in `tests/e2e/test_processes_gateway.py`:
- `test_group_alive_tolerates_a_malformed_or_truncated_stat_line`: a fabricated
  `/proc`-shaped tmp dir with three malformed entries (empty content, no `)` at all with a
  non-numeric third field, and a well-formed `)` but too few fields after it) --
  `group_alive` returns `False`, never raises.
- `test_group_alive_still_finds_a_well_formed_match_past_malformed_entries`: the same three
  malformed entries plus one well-formed, genuinely-matching entry -- `group_alive` still
  returns `True`, proving the widened tolerance doesn't swallow a real match (the plan's
  own stated risk).
- `test_group_alive_returns_a_bool_never_raises_on_the_real_host`: `group_alive` against a
  real spawned process with `held` non-empty, on this host.

Proof the test fails pre-fix for the right reason: reverted just the new
`try`/`except (IndexError, ValueError)` block (keeping the `proc_root` plumbing) and reran
-- both malformed-shape tests failed with a raw `IndexError: list index out of range` at
`fields[0], fields[2]` inside `_group_alive_proc_scan`, the exact escape this task
describes. Re-applied the fix: all three new tests pass, and `just done` is fully green
(lint, typecheck, gates, pypeeker rule tests, unit, integration x2, e2e, docs, architecture
lint -- 169/169 relevant tests passed, no regressions).
<!-- SECTION:NOTES:END -->
