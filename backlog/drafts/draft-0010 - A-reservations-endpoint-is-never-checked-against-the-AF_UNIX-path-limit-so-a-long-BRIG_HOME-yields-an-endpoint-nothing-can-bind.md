---
id: DRAFT-0010
title: >-
  A reservation's endpoint is never checked against the AF_UNIX path limit, so a
  long BRIG_HOME yields an endpoint nothing can bind
status: Draft
assignee: []
created_date: '2026-10-19 13:00'
labels:
  - brig
  - channels
  - size-1
dependencies: []
parent_task_id: TASK-0001
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-0001.25's review. domain/channels.py's reserve() derives a reservation's endpoint by joining the channel directory and the name, but never checks the result against the AF_UNIX sun_path limit (about 108 bytes on Linux, 104 on macOS). A long BRIG_HOME (or a long channel name) yields an endpoint that bind() and connect() will refuse, and nothing says so until the jailed program fails to listen.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 reserve refuses, as a value (not raised), an endpoint longer than the platform's AF_UNIX path limit; a unit test pins it
<!-- AC:END -->
