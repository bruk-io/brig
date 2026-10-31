---
id: TASK-0021
title: Grade a bwrap jail's fs_write, network, fs_read and env
status: To Do
assignee:
  - '@claude'
created_date: '2026-10-31T11:00:00Z'
labels:
  - size-5
dependencies: []
references:
  - >-
    backlog/tasks/task-0001.18 -
    Grading-skeleton-claims-evidence-and-grade-unenforced-by-default-independent-of-the-supervisor.md
type: task
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder that shows its person how well a jail holds wants one grade per axis of enforcement: what the command may write (`fs_write`), reach on the network (`network`), read (`fs_read`) and see of the environment (`env`), as the old brig graded them. At a7e7f45 brig states one claim, `CHANNEL_EXCLUSIVITY_CLAIM`; TASK-0001 criterion #5 keeps grades, and the grading skeleton (TASK-0001.18) is unenforced by default until evidence proves otherwise.

Each claim's grade must come from evidence, never be stated ahead of it (law: grades are honest). A path masked with a bind is enforced only while the host leaves the masked entry alone: an embedder that knows the host may replace it needs the grade to say best-effort, or the evidence to let it decide.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A bwrap jail's compile states a claim for each of fs_write, network, fs_read and env, re-exported from brig like CHANNEL_EXCLUSIVITY_CLAIM
- [ ] #2 Each claim is graded from evidence an e2e battery produces against real bwrap, and none grades stronger than that battery shows
- [ ] #3 With no evidence, each grades unenforced (TASK-0001.18's default)
<!-- AC:END -->
