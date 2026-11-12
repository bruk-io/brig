---
id: TASK-0064
title: 'On darwin, a jail outlives an embedder killed with SIGKILL'
status: To Do
assignee: []
created_date: '2026-11-12 19:08'
labels:
  - darwin
  - security
dependencies: []
type: bug
ordinal: 59000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by bh-02 TASK-0196 (2026-11-12). Seatbelt has nothing like bwrap's --die-with-parent. When the embedder is killed with SIGKILL, the supervisor dies, but an input's background program (in the jail's group, or after setsid) and the jail's freezer keep running, still sandboxed. A normal destroy_jail tears everything down. bh-02's test of this is a strict xfail on darwin.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On darwin, after the embedder is killed with SIGKILL, no process of its jail survives (or the next create reaps it, with the gap stated in the grades and spec)
- [ ] #2 An e2e test kills the embedder with SIGKILL and checks for survivors
<!-- AC:END -->
