---
id: DRAFT-0021
title: >-
  A jail reopens its stdio files through /proc/self/fd with more rights than
  brig granted
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - brig
  - stdio
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (demonstrated in real bwrap 0.9.0): a jail with no writable root opened /proc/self/fd/0 O_WRONLY|O_TRUNC and overwrote the host's stdin file, and opened /proc/self/fd/1 O_RDONLY to read the append-only stdout file, while the report said fs_write, fs_read and channel_exclusivity ENFORCED. The magic link reopens the inode and permission is checked on the file's mode for the same uid. INHERIT is affected too (an embedder's log file as stdout). Proposed: never hand the jail an fd on a host inode: pipes, pumped by the host to and from the files; count stdio as a shared medium under law 9.
<!-- SECTION:DESCRIPTION:END -->
