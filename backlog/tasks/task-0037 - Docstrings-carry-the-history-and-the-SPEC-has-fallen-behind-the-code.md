---
id: TASK-0037
title: Docstrings carry the history and the SPEC has fallen behind the code
status: To Do
assignee: []
created_date: '2026-11-02T17:23:00Z'
labels:
  - size-3
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. 3,203 of 5,583 source lines (57%) are docstrings, with about 330 TASK/decision references (`plan.py` is 82% docstring), much of it narrating history. Some is already false: `_AwaitSupervisorDone` is referenced and does not exist (`effects.py`, `wire.py`); `env.py` and `effects.py` say there is no `frozendict`, which is a builtin on 3.15.0b4, so rule 8 is broken on a false premise. `docs/spec/index.md` lists claims, grades, sockets, supervisor and report as reserved, not built, against rule 18. Dead weight alongside: `Spawn` and `Reap` are never constructed but keep their driver arms, three port methods and adapters alive; each of ProcessUnknown, SupervisorDoneUnknown and the readiness outcomes exists three times (infra, ports, domain); three classes are named `ChannelRefused` with two meanings (rule 12); `LiveSupervisors` keys a dict that never holds more than one entry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Docstrings state the contract; history lives on the board
- [ ] #2 The SPEC describes what is built, and frozendict replaces the dict workarounds
- [ ] #3 The unused effects and their ports are gone, and one name means one thing
<!-- AC:END -->
