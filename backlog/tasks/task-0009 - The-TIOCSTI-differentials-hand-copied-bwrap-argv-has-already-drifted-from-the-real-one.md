---
id: TASK-0009
title: >-
  The TIOCSTI differential's hand-copied bwrap argv has already drifted from the
  real one
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:55'
updated_date: '2026-10-18 13:20'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - tests/e2e/test_tiocsti_battery.py
  - tests/unit/test_bwrap_compile.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/e2e/test_tiocsti_battery.py's _BWRAP_ARGV_PREFIX (line 131) is a hand-maintained copy of the real jail argv, kept as a literal rather than an import because decision-0001 rule 4 bars an e2e test from importing a domain module. It has already drifted: the real argv built by domain/jail_types/bwrap.py's compile_supervisor_launch now carries --as-pid-1 between --new-session and -- (TASK-0001.15 step 4; asserted in tests/unit/test_bwrap_compile.py), and the copy does not. Its own docstring also still cites a constant that no longer exists (_BWRAP_ARGV; the real names are _NAMESPACE_FLAGS plus _compile_binds).

Impact today is documentation-grade, not a false pass: --as-pid-1 is PID-namespace reaping and does not touch session or controlling-terminal semantics, so the differential TASK-0001.11 committed still isolates --new-session correctly and TASK-0001.05 AC#2's attribution still holds. The risk is forward-looking: this copy is precisely the artifact meant to notice when the real argv moves, and on its first opportunity it did not. A future flag that does affect the terminal could be added to the real argv while the differential keeps grading a stale one.

The fix is a fidelity assertion rather than an import (rule 4 stands): something that fails when the copy and the real compiled argv diverge -- e.g. a unit or integration test that may import domain and asserts the e2e literal is a subsequence of / equal to compile_supervisor_launch's output, or the e2e test deriving its prefix from the public API.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The TIOCSTI differential's bwrap argv cannot silently diverge from the argv compile_supervisor_launch actually builds: a check fails when it does, without an e2e test importing a domain module
- [ ] #2 The copy's docstring names constants that exist in domain/jail_types/bwrap.py today
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Fix the immediate drift: add `--as-pid-1` to `_BWRAP_ARGV_PREFIX` so it matches
   `compile_supervisor_launch`'s real output again; fix the docstring citing the
   no-longer-existing `_BWRAP_ARGV` constant (real names: `_NAMESPACE_FLAGS` +
   `_compile_binds`).
2. Build the fidelity assertion both DRAFT-0011 and this task's own AC#1 ask for,
   without an e2e test importing a domain module (rule 4 stands): a unit or
   integration-layer test (which MAY import domain) asserting the e2e literal is
   equal to (or a subsequence of) `compile_supervisor_launch`'s actual compiled
   output for the same policy -- so a future change to the real argv that isn't
   mirrored in the e2e copy fails loudly, in a layer that's allowed to know both.

### Proof
- just gates, just done green.
- Delete this task's own fix to `_BWRAP_ARGV_PREFIX` temporarily and confirm the
  new fidelity check fails (proving it's discriminating, not just present), then
  restore it.

### Risks
- Low: --as-pid-1 affects PID-namespace reaping, not session/terminal semantics, so
  TASK-0001.11's own differential conclusion is unaffected by this fix -- confirm
  that remains true, don't just assert it.
<!-- SECTION:PLAN:END -->
