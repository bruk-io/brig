---
id: DRAFT-0015
title: >-
  The TIOCSTI differential's hand-copied bwrap argv has already drifted from the
  real one
status: Draft
assignee: []
created_date: '2026-10-18 12:55'
labels: []
dependencies: []
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
