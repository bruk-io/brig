---
id: TASK-0042
title: >-
  A jail reopens its stdio files through /proc/self/fd with more rights than
  brig granted
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T17:50:00Z'
labels:
  - brig
  - stdio
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (demonstrated in real bwrap 0.9.0): a jail with no writable root opened /proc/self/fd/0 O_WRONLY|O_TRUNC and overwrote the host's stdin file, and opened /proc/self/fd/1 O_RDONLY to read the append-only stdout file, while the report said fs_write, fs_read and channel_exclusivity ENFORCED. The magic link reopens the inode and permission is checked on the file's mode for the same uid. INHERIT is affected too (an embedder's log file as stdout). Proposed: never hand the jail an fd on a host inode: pipes, pumped by the host to and from the files; count stdio as a shared medium under law 9.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No jail is handed an fd on a host inode for stdio: a PATH or INHERIT stdio reaches the jail as a pipe the host pumps to and from the file (or the embedder's own stream), so reopening /proc/self/fd/N reaches only the pipe
- [ ] #2 An e2e battery reopens each stdio fd through /proc/self/fd with a wider mode (truncate stdin's file, read the append-only stdout file) and fails if the host file changes or is read; recorded failing before the fix
- [ ] #3 Pumping ends with the jail: destroy_jail drains and closes the pumps, and a jail that never reads stdin or floods stdout cannot block the host past destroy (law 7)
- [ ] #4 The spec counts stdio among the media law 9 names, and channel_exclusivity's claim text says what stdio carries
<!-- AC:END -->
