---
id: TASK-0038
title: brig-no-patching fails the gate on test_report_battery's os.environ writes
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T04:14:00Z'
updated_date: '2026-11-03T04:21:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
At HEAD of claude/embedder-gaps, uv run just gates (and so just done) exits 1. TASK-0033's _attribute_writes_on_imports fires twice on tests/e2e/test_report_battery.py:117-118 (os.environ[...] = ...). That file was already there at 282295b, so TASK-0033's 'just done green' must have been measured on another tree (its output shows /home/user/brig-gates). The message also says 'assigns an attribute' when the write is a subscript. Changing the host's environment from inside a test is the host not entering as data (decision-0001 rule 5).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 test_report_battery's env case hands the jail its environment as data, with no write to os.environ, and uv run just done passes at HEAD
- [x] #2 The message for a subscript write through an import names it as one
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03. Fixed at fe3f40d: tests/e2e/test_report_battery.py's env case passes its candidate environment to create_bwrap_jail as data instead of writing os.environ, so brig-no-patching's new part passes; the part's message now says it covers item writes (os.environ[...]) as well as attributes. uv run just done passes.
<!-- SECTION:NOTES:END -->
