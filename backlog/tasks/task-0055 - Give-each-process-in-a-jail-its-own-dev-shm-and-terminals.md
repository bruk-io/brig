---
id: TASK-0055
title: Give each process in a jail its own /dev/shm and terminals
status: To Do
assignee: []
created_date: '2026-11-10 17:16'
labels:
  - isolation
  - security
  - size-3
dependencies: []
type: task
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From bh-02's port onto bruk-io/brig v0.1.0: the old in-repo brig had this and this brig does not. Measured in bh-02 (decision-211, decision-212 in libs/brig/SPEC.md at bh-02 commit d0c3a416 (its in-repo libs/brig, removed by bh-02's port to this brig)), in one jail holding two processes with namespaces: B read and changed A's file in /dev/shm, and listed, opened and typed into A's terminal (/dev/pts/N), and A received the bytes; two separate jails kept both apart. The old brig's fix, in libs/brig/src/brig/run/_supervisor_program.py isolate(): a fresh tmpfs on /dev/shm and a new devpts instance on /dev/pts for each process with namespaces, carrying Spec mounts under /dev/shm onto the new tmpfs (held by O_PATH descriptors, bound back recursively) so decision-198 stays true, and the probe runs the same code. Also measured: a Spec mount exactly on /dev/shm stays shared; flock on the jail's own objects (/, /dev) is a channel in one jail only; each /dev/shm is half of RAM with no size= limit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Two processes in one jail with namespaces cannot read, change or list each other's /dev/shm files or terminals, shown by a test with a control that fails without the isolation
- [ ] #2 Spec mounts under /dev/shm stay visible to the process, shown by a test
<!-- AC:END -->
