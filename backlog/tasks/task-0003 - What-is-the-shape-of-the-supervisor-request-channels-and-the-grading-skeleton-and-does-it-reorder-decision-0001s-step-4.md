---
id: TASK-0003
title: >-
  What is the shape of the supervisor, request channels, and the grading
  skeleton -- and does it reorder decision-0001's step 4?
status: Done
assignee: []
created_date: '2026-10-18 02:27'
updated_date: '2026-10-18 02:46'
labels:
  - brig
  - size-5
dependencies: []
references:
  - >-
    backlog/decisions/decision-0002 -
    The-supervisor-request-channels-and-the-grading-skeleton-the-next-slices-shape.md
parent_task_id: TASK-0001
type: design
ordinal: 14000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decision recorded
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review (reviewer did not do the work): closed. AC #1 "Decision recorded" holds. The referenced decision exists at backlog/decisions/decision-0002 - The-supervisor-request-channels-and-the-grading-skeleton-the-next-slices-shape.md, is substantive rather than a stub (Context tracing the supervisor's real dependencies, five numbered rulings, Consequences, and a revised order for decision-0001's step 4), carries status: accepted with an Acceptance section recording the owner's acceptance on 2026-10-18, and is referenced from this task's frontmatter references:. It is referenced back from TASK-0001 in four settled/carried-forward open questions (reservations, egress, Seatbelt, the log envelope) and in its References list. board-check close TASK-0003: ok, exit 0.

Findings, neither blocking:
- Low: TASK-0001's References list (line 71) still calls decision-0002 "(proposed)" while line 70 calls decision-0001 "(accepted)". The decision is accepted; the parent's reference is stale. A one-word correction for whoever owns TASK-0001's description - too small to earn a task, and outside a reviewer's allowed edits. Filed nowhere.
- Low: decision-0002's entire ## Acceptance block is an uncommitted working-tree change (alongside uncommitted edits to decision-0001 and task-0002). The committed frontmatter already says status: accepted, so the criterion holds, but this close commits only the task file. The owner should commit the decision file so the acceptance record this close rests on is on the branch. Filed nowhere.

Check not run, recorded deliberately: record-check --tier full was skipped. The criterion is documentary - ruff, mypy, the test suites, the docs build and the architecture lint produce no evidence about whether a decision was recorded - and the tree is dirty with several sibling agents' in-progress work, where a check that reformats files as it runs would collide with it (and would itself be a finding).
<!-- SECTION:NOTES:END -->
