---
id: TASK-0032
title: >-
  channel_exclusivity counts only writable shared paths, but a read-only bind of
  a host directory holding a socket is dialable
status: To Do
assignee: []
created_date: '2026-10-31T14:41:00Z'
updated_date: '2026-11-02T17:23:00Z'
labels:
  - size-3
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0019 (2026-10-31). A Unix socket accepts a connect through a read-only mount and across bwrap's network namespace: connect() needs search on the path, not write. `CHANNEL_EXCLUSIVITY_CLAIM` is defined over *writable* shared paths (`writable_shared_paths`), so a policy that binds, read-only, a host directory holding someone else's listening socket (the default `WHOLE_HOST_READ_ONLY` binds all of `/`: `/run`, `/tmp`, the session bus, a container runtime's socket) lets the jail dial out to it with the claim still graded enforced. TASK-0019 removes the one such medium brig added on its own (its state directory); this is the general question, and it is a definition change, so it is the owner's.

Measured: TASK-0019's reproduction dialled through brig's read-only state-directory bind.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision recorded: whether channel_exclusivity (old SPEC law 9) covers dialable read-only media, and if so how they are enumerated and what the default policy then grades
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Architecture review, 2026-11-02, measured under the shipped default (no policy given): a host listener at /run/brig_review_host.sock, and the jail dialled it and read its answer (JAIL-DIALED-HOST b'HOST-SECRET'). So under WHOLE_HOST_READ_ONLY a jailed command can reach the session bus, a container runtime's socket, anything under /run or /tmp, while channel_exclusivity grades enforced. Severity: high.
<!-- SECTION:NOTES:END -->
