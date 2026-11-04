---
id: DRAFT-0033
title: >-
  test_report_battery's mask-renamed-over test raised JailExitUnknown once under
  heavy load
status: Draft
assignee: []
created_date: '2026-11-04T15:17:00Z'
labels:
  - brig
  - tests
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen once by TASK-0053's worker, 2026-11-04, under a load heavier than the full tier: test_report_battery.py::test_fs_read_a_mask_the_host_renames_over_is_undone_so_the_report_says_best_effort failed with JailExitUnknown. Unknown whether the test's timing or brig's exit-code path; name the cause under the same load, then fix the test or file a brig bug.
<!-- SECTION:DESCRIPTION:END -->
