---
id: TASK-0045
title: Readiness ignores its deadline and dials a planted link before refusing it
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:31:00Z'
labels:
  - brig
  - channels
  - size-3
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (both demonstrated): (a) a jail that calls listen(0) and fills its own backlog makes await_channel_ready(timeout_s=2) block for 10 s (the blocking connect in infra/sockets.py ignores the deadline; law 7). (b) a link planted at the reserved name is dialled as the embedder before PEER_OUTSIDE_JAIL refuses it, so a socket-activated host service is triggered. Proposed: hold the channel directory's fd from creation; openat(dirfd, name, O_PATH|O_NOFOLLOW), require S_ISSOCK, connect non-blocking to /proc/self/fd/N with a poll deadline (the reviewer checked both work).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 await_channel_ready honours timeout_s against a jail that fills its own listen backlog and never accepts: it returns ChannelNotReady (or a terminal outcome) within the deadline plus a small bound; e2e recorded failing before the fix
- [ ] #2 A link planted at the reserved name is refused without the embedder connecting to what it names: brig opens the name beneath a directory fd it holds from creation with O_PATH|O_NOFOLLOW, requires a socket, and connects through that fd non-blocking with a poll deadline; e2e shows a host listener behind the link sees no connection; recorded failing before the fix
- [ ] #3 The returned connection is still the verified one (TASK-0001.34) and the readiness battery still passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
