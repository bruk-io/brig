---
id: TASK-0058
title: 'Readiness: wait until a started process listens on its reserved channel'
status: To Do
assignee: []
created_date: '2026-11-10 17:16'
labels:
  - channels
  - size-3
dependencies: []
type: task
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From bh-02's port onto bruk-io/brig v0.1.0: this brig has no wait_ready. The old in-repo brig (bh-02 commit d0c3a416 (its in-repo libs/brig, removed by bh-02's port to this brig), libs/brig/src/brig/run/readiness.py, Process.wait_ready then Process.connect, decision-185) gave an embedder reserve-then-start: brig reserves each process's socket in the channel directory, the embedder puts the in-jail path in argv, waits on readiness through the verified dial, then dials. bh-02's runner contract was built on it (bh-02 TASK-0079.31). Note for whoever builds it: a readiness probe takes a listen-backlog slot, so a workload with listen(1) can refuse the next dial (bh-02 TASK-0215, measured 243 refusals in 1500 starts under load).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An embedder can wait until a started process accepts on its reserved channel, through the verified dial, with a timeout, shown by tests
- [ ] #2 The spec states that readiness takes a backlog slot
<!-- AC:END -->
