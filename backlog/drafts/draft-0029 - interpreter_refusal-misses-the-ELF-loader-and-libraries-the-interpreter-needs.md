---
id: DRAFT-0029
title: interpreter_refusal misses the ELF loader and libraries the interpreter needs
status: Draft
assignee: []
created_date: '2026-11-04T12:40:00Z'
labels:
  - brig
  - fs-policy
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Split from TASK-0052 (was DRAFT-0020), 2026-11-04: a policy that mounts the interpreter but not its ELF loader (PT_INTERP) and the libraries it needs (DT_NEEDED) passes interpreter_refusal, then fails in bwrap with execvp No such file or directory and JailExitUnknown (reproduced at aadf8ba with FsPolicy(readable=(.venv, ~/.local/share/uv/python))). The question is the approach: parse PT_INTERP and DT_NEEDED and search ld.so.cache and RPATH in the standard library, or have the start report bwrap's execvp failure as a typed error. Decide before building.
<!-- SECTION:DESCRIPTION:END -->
