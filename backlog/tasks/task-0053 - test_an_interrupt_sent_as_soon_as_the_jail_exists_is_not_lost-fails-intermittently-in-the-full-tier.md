---
id: TASK-0053
title: >-
  test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost fails
  intermittently in the full tier
status: To Do
assignee: []
created_date: '2026-11-04T14:23:00Z'
updated_date: '2026-11-04T14:24:00Z'
labels:
  - brig
  - tests
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reviewing TASK-0050/0001.38/0051/0052 on claude/small-bugs (2026-11-04): five full-tier runs (record-check --tier full) of one tree failed twice, both times only tests/e2e/test_interrupt_battery.py::test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost (recorded on TASK-0050 and TASK-0052); three passed. Alone it passed 3 of 3 and 8 of 8 run in parallel. TASK-0047's worker saw an unnamed full-tier e2e failure of the same kind. The branch does not touch the signal path (signal_jail_pid1 and _pid1_under; the change is to _nspid and jail_pid1_namespace). record-check keeps only the tail of the output, so neither assertion message was kept: which of the test's two asserts fires is unknown. Realistic path: CI under load goes red on a change that has nothing to do with it, or a lost-interrupt window that TASK-0030 closed is open again under load.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The failing assert and its cause are identified, from a run that keeps the test's output
- [ ] #2 The test passes 10 full-tier runs in a row, or the window it shows is fixed with a test that pins it
- [ ] #3 The failing assert of test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost is named, with its message, from runs under load (the full tier, or the e2e layer run with other e2e tests in parallel) until it fails at least 3 times
- [ ] #4 The cause is found and stated: a flaw in the test (a timing assumption) or a lost interrupt in brig (TASK-0030's window open again); if brig's, a repro is recorded and the fix keeps the interrupt from being lost
- [ ] #5 The test passes 50 of 50 runs under the same load
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
