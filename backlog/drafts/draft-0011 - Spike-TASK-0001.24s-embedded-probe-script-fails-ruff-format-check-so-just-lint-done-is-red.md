---
id: DRAFT-0011
title: >-
  Spike TASK-0001.24's embedded probe script fails ruff format --check, so just
  lint/done is red
status: Draft
assignee: []
created_date: '2026-10-19 13:07'
labels:
  - brig
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ruff format --check . formats python fenced blocks in markdown. The verbatim probe.py in TASK-0001.24's implementation notes (backlog/tasks/task-0001.24 ... .md:172) would be reformatted, so just lint and just done fail on main for every task (seen in the reviewer's full-tier record-check, 2026-10-19). Fix by excluding backlog/ from ruff format, or by fencing the probe as text, without rewriting the measured script's content.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 just done passes on main
- [ ] #2 The probe script recorded in TASK-0001.24 stays verbatim
<!-- AC:END -->
