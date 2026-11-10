---
id: TASK-0060
title: 'Run several programs in one jail, each kept apart'
status: To Do
assignee: []
created_date: '2026-11-10 17:16'
updated_date: '2026-11-10 17:16'
labels:
  - isolation
  - security
  - size-5
dependencies:
  - TASK-0055
type: task
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From bh-02's port onto bruk-io/brig v0.1.0. bh-02 TASK-0074 (Done before the port, dropped by it) ran a session's Python process and extensions process in one jail where the old in-repo brig (bh-02 commit d0c3a416 (its in-repo libs/brig, removed by bh-02's port to this brig)) gave each process its own namespaces, and a jail per program elsewhere (Process.namespaces false: uid 0, blocked user namespaces, a refused mount). It needed from brig: start more than one program in one jail; report per process whether it has namespaces of its own; per-process channel and scratch directories; the per-process /dev/shm and terminals task; reads decided at create, a later start outside them refused. bh-02's measurements of what one shared jail exposes are in its TASK-0074 notes. Depends on the per-process /dev/shm and terminals task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An embedder can start several programs in one jail and learn whether each has namespaces of its own
- [ ] #2 Two programs in one jail with namespaces cannot reach each other's sockets, files, terminals, signals or IPC, shown by an attack test with a positive control
<!-- AC:END -->
