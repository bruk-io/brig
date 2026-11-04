---
id: DRAFT-0032
title: >-
  interrupt_jail's promise does not say a command can swallow an interrupt that
  arrives during its own startup
status: Draft
assignee: []
created_date: '2026-11-04T15:19:00Z'
labels:
  - brig
  - docs
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
docs/spec/index.md:48 says interrupt_jail 'loses nothing'. TASK-0053 found that brig delivers an early SIGINT, but a Python command interrupted during interpreter startup can raise KeyboardInterrupt inside an importlib weakref callback, report it as ignored and carry on (1 of 580 with no jail; 2 of 992 in-jail under load), so the command exits 0 and an embedder reads it as lost. Realistic path: an embedder whose jailed command is Python interrupts right after create and sees no effect. Brig cannot fix the interpreter; the promise should say where delivery ends.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The spec's interrupt_jail promise says it guarantees delivery to the command, not that the command dies, and names a Python command's startup as a case where the interrupt can be swallowed
<!-- AC:END -->
