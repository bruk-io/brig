---
id: TASK-0056
title: Say loudly when a refused mount costs a process its namespaces
status: To Do
assignee: []
created_date: '2026-11-10 17:16'
updated_date: '2026-11-10 17:16'
labels:
  - isolation
  - security
  - size-2
dependencies:
  - TASK-0055
type: task
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From bh-02's port onto bruk-io/brig v0.1.0. In the old in-repo brig (bh-02 commit d0c3a416 (its in-repo libs/brig, removed by bh-02's port to this brig), libs/brig/src/brig/run/_supervisor_program.py and test_namespaces_lost.py), a host that refused the per-process tmpfs, devpts or carried mounts made the process lose all its namespaces, and the owner of bh-02 ruled that must be loud and clear: Jail.create raised a NamespacesLost warning naming the refused mount and what was lost, or called an embedder's told= instead. Other refusals (/proc, MS_PRIVATE, channel or scratch binds) and the uid 0 and blocked-user-namespace fallbacks stayed silent. Depends on the per-process /dev/shm and terminals task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When a mount brig needs for per-process isolation is refused, an embedder gets a warning or a callback naming the mount and what was lost, shown by tests that plant each refusal
- [ ] #2 Which fallbacks stay silent is stated in the spec
<!-- AC:END -->
