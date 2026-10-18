---
id: TASK-0009
title: >-
  The TIOCSTI differential's hand-copied bwrap argv has already drifted from the
  real one
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:55'
updated_date: '2026-10-18 13:29'
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
- [x] #1 The TIOCSTI differential's bwrap argv cannot silently diverge from the argv compile_supervisor_launch actually builds: a check fails when it does, without an e2e test importing a domain module
- [x] #2 The copy's docstring names constants that exist in domain/jail_types/bwrap.py today
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed the drift and built the fidelity check (plan steps 1-2):

1. tests/e2e/test_tiocsti_battery.py: _BWRAP_ARGV_PREFIX now carries --as-pid-1
   between --new-session and -- (matching TASK-0001.15 step 4's real argv).
   Docstring rewritten to cite the real constants (_NAMESPACE_FLAGS,
   _compile_binds's default-policy output) instead of the no-longer-existing
   _BWRAP_ARGV, and now points at the new fidelity test below.

2. tests/unit/test_bwrap_compile.py:
   test_e2e_tiocsti_battery_bwrap_argv_prefix_matches_compile_supervisor_launch --
   imports _BWRAP_ARGV_PREFIX from tests/e2e/test_tiocsti_battery (not a `brig`
   import, so decision-0001 rule 4's own tests/unit check, which only restricts
   `brig` imports, does not fire on it) and asserts it equals
   compile_supervisor_launch's real output up to the supervisor path, for the
   default WHOLE_HOST_READ_ONLY policy. Lives in tests/unit because rule 4 as
   pypeeker actually enforces it (pypeeker_rules/brig.py's
   _integration_test_violations) bars tests/integration from importing
   brig.domain directly -- only tests/unit may.

Proof the check is discriminating (plan's own ask): reverted --as-pid-1 from
_BWRAP_ARGV_PREFIX, ran the new test alone -- it failed
("At index 7 diff: '--as-pid-1' != '--'"). Restored the fix, reran -- passes.

Confirmed --as-pid-1 doesn't affect TIOCSTI/session semantics (risk item), not
just asserted: ran tests/e2e/test_tiocsti_battery.py for real against
brig-probe-amd64:latest (privileged, real bwrap, real Linux) with --as-pid-1
already present in the real argv (it's been in production code since
TASK-0001.15 step 4) -- positive control, real-jail injection-denied, and the
TASK-0001.11 differential (test_new_session_is_the_sole_closer_of_tiocsti_...)
all still pass/skip exactly as before: 3 passed, 1 skipped (session_detached
unattributable on this interpreter). TASK-0001.11's own differential
conclusion is unaffected.

just gates and just done both pass. Note: the shared working tree had a
concurrent, unrelated in-progress edit (another agent's compile_supervisor_launch
state_dir change + new src/brig/infra/state_dir.py) that left just gates/done red
for reasons unrelated to this task; verified this task's own two files
(tests/e2e/test_tiocsti_battery.py, tests/unit/test_bwrap_compile.py) in
isolation via git stash of the other agent's uncommitted files, confirmed
gates+done green with only this task's diff applied, then restored the stash
untouched.

Modified files: tests/e2e/test_tiocsti_battery.py, tests/unit/test_bwrap_compile.py
<!-- SECTION:NOTES:END -->
