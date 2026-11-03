---
id: TASK-0031
title: >-
  A stdio path is opened through a symlink, so a jail can redirect the next
  jail's output into any file the embedder can write
status: To Do
assignee: []
created_date: '2026-11-03T03:31:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0028 (d98bc84). infra/supervisor/link.py _open_stdio opens stdout/stderr with O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC in brig's own process: no O_NOFOLLOW, and the 0600 mode applies only when the file is created. When an embedder names a stdio path inside a root the jail can write (a log beside the work, reused across runs), the jailed command can replace it with a symlink to, say, ~/.bashrc, and the next create_bwrap_jail appends that jail's output there with the embedder's permissions; stdin likewise reads any file the embedder can. Not measured.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A stdio path whose last component is a symlink is refused (O_NOFOLLOW or equivalent), or a stdio path under a writable root is refused at create, with an error saying what to do
- [ ] #2 An e2e test plants the symlink from inside a jail and shows the next create does not write through it
<!-- AC:END -->
