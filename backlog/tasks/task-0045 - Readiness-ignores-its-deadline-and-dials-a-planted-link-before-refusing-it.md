---
id: TASK-0045
title: Readiness ignores its deadline and dials a planted link before refusing it
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - brig
  - channels
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (both demonstrated): (a) a jail that calls listen(0) and fills its own backlog makes await_channel_ready(timeout_s=2) block for 10 s (the blocking connect in infra/sockets.py ignores the deadline; law 7). (b) a link planted at the reserved name is dialled as the embedder before PEER_OUTSIDE_JAIL refuses it, so a socket-activated host service is triggered. Proposed: hold the channel directory's fd from creation; openat(dirfd, name, O_PATH|O_NOFOLLOW), require S_ISSOCK, connect non-blocking to /proc/self/fd/N with a poll deadline (the reviewer checked both work).
<!-- SECTION:DESCRIPTION:END -->
