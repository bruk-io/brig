---
id: TASK-0059
title: >-
  Decide what the verified dial does when a server closes before its peer is
  read
status: To Do
assignee: []
created_date: '2026-11-10 17:16'
labels:
  - channels
  - darwin
  - size-2
dependencies: []
type: task
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From bh-02's port onto bruk-io/brig v0.1.0. The old in-repo brig (bh-02 commit d0c3a416 (its in-repo libs/brig, removed by bh-02's port to this brig), libs/brig/SPEC.md decision-209 and decision-210, libs/brig/src/brig/run/dial.py) measured that darwin's LOCAL_PEERPID read fails with ENOTCONN once the serving end has closed, while Linux keeps SO_PEERCRED. Its owner ruled the dial refuses such a server at once (never trusting an unverified peer), that a LISTEN workload holds each connection until the host closes it, and that the refusal says so in its message. This brig has a peer-credential dial too: check whether it meets the same case, and rule on it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The dial's behaviour for a server that closes first is ruled in the spec, with the refusal's message saying what to do
- [ ] #2 A test forces the race and shows the dial refuses
<!-- AC:END -->
