---
id: DRAFT-0030
title: >-
  test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost fails
  intermittently in the full tier
status: Draft
assignee: []
created_date: '2026-11-04T14:23:00Z'
labels:
  - brig
  - tests
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
<!-- AC:END -->
