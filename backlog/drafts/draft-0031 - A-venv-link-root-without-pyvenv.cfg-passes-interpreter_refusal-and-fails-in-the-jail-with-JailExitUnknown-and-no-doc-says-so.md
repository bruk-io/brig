---
id: DRAFT-0031
title: >-
  A venv-link root without pyvenv.cfg passes interpreter_refusal and fails in
  the jail with JailExitUnknown, and no doc says so
status: Draft
assignee: []
created_date: '2026-11-04T14:23:00Z'
labels:
  - brig
  - fs-policy
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Since TASK-0052 (e39e676), interpreter_refusal stops at a chain path that is itself a root, so FsPolicy(readable=(system, uv's python dir, .venv/bin/python3)) without .venv/pyvenv.cfg is no longer refused (before, it was refused by the over-refusal TASK-0052 removed). In the jail the interpreter is a plain file at the link's path, finds no pyvenv.cfg and no standard library (ModuleNotFoundError: No module named 'base64', measured by TASK-0052's worker), and run_jail raises JailExitUnknown. The same class as DRAFT-0029 (the interpreter needs more than its link chain), which names only the ELF loader and libraries. Neither docs/spec/index.md nor interpreter_refusal's docstring says that a root on the venv link also needs pyvenv.cfg and the base install's prefix, so an embedder learns it only from a JailExitUnknown.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 interpreter_refusal's docstring and the SPEC's interpreter_refusal line say that a root on the venv's python link also needs the venv's pyvenv.cfg and the base install's prefix, and that until DRAFT-0029 is decided such a policy fails in the jail with JailExitUnknown
- [ ] #2 DRAFT-0029's question covers pyvenv.cfg and the prefix as well as PT_INTERP and DT_NEEDED, or this is decided alongside it
<!-- AC:END -->
