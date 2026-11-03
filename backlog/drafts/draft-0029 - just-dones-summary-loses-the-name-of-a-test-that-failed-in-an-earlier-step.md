---
id: DRAFT-0029
title: just done's summary loses the name of a test that failed in an earlier step
status: Draft
assignee: []
created_date: '2026-11-03T19:53:00Z'
updated_date: '2026-11-03T19:59:00Z'
labels:
  - brig
  - tooling
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
2026-11-03: an e2e test failed once in TASK-0047's first full-tier run and nobody could name it: record-check keeps only the tail of just done's output, and the docs and architecture steps print after the e2e step's pytest summary. Earlier the same day test_interrupt_battery's test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost failed once and then passed. Proposed: done's final summary repeats each failed step's FAILED/ERROR lines (pytest -rfE output), so a flaky test is named in any record, then the flake can be judged.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Done directly in 1515fbc (a handful of lines, no task needed): test-selected's -rs had replaced pytest's default fE, so FAILED lines were never printed; it is now -rfEs, and run_done repeats each failed step's FAILED/ERROR lines last. Checked with a deliberately failing test outside the repository.
<!-- SECTION:NOTES:END -->
