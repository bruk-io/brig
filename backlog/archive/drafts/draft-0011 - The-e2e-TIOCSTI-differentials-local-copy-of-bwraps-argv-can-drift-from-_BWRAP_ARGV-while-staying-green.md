---
id: DRAFT-0011
title: >-
  The e2e TIOCSTI differential's local copy of bwrap's argv can drift from
  _BWRAP_ARGV while staying green
status: Draft
assignee: []
created_date: '2026-10-18 04:43'
updated_date: '2026-10-18 13:20'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0001.11 added `test_new_session_is_the_sole_closer_of_tiocsti_when_infra_detaches_no_session` to `tests/e2e/test_tiocsti_battery.py`. It cannot import `domain/jail_types/bwrap.py` (decision-0001 rule 4 bars a domain import from tests/e2e/, and no public entry point hands back a compiled Plan's argv), so it hand-copies that module's `_BWRAP_ARGV` into a local `_BWRAP_ARGV_PREFIX`. The two are byte-identical today (verified at TASK-0001.11's close).

The failure mode is not a break, it is a silent loss of meaning: if `_BWRAP_ARGV` changes and the copy does not, the test keeps passing -- bwrap with the stale argv still denies TIOCSTI with --new-session and still injects without it -- while no longer grading brig's real argv at all. Nothing in the suite catches that drift mechanically; the test's own docstring states the obligation as prose on whoever next edits the jail type.

This is imminent rather than hypothetical: TASK-0001.16 (Filesystem policy, In Progress) is specifically chartered to replace the `--ro-bind / /` entry in `_BWRAP_ARGV`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A change to domain/jail_types/bwrap.py's _BWRAP_ARGV that is not mirrored in the e2e differential's copy causes a test in the suite to fail
- [ ] #2 The chosen mechanism (public accessor, pypeeker rule exemption, equality assertion, or other) does not weaken decision-0001 rule 4's bar on domain imports from tests/e2e/
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Superseded by TASK-0009 (promoted from DRAFT-0015), which found the drift this draft predicted had actually happened (--as-pid-1 missing from the e2e differential's hand-copied argv) and carries the same fidelity-assertion fix. Archiving rather than promoting this one to avoid two tasks for one fix.
<!-- SECTION:NOTES:END -->
