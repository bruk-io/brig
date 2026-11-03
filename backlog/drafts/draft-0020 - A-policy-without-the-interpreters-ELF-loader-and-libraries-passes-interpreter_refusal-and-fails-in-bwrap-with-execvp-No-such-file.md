---
id: DRAFT-0020
title: >-
  A policy without the interpreter's ELF loader and libraries passes
  interpreter_refusal and fails in bwrap with execvp No such file
status: Draft
assignee: []
created_date: '2026-11-03T03:46:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0029 at 55336cd. FsPolicy(readable=(.venv, ~/.local/share/uv/python)) passes interpreter_refusal; create_bwrap_jail then prints 'bwrap: execvp /home/user/brig/.venv/bin/python3: No such file or directory' and run_jail raises JailExitUnknown, the exact symptom TASK-0029 set out to replace: the dynamic loader (/lib64/ld-linux-*) and libc are not mounted. Also over-refuses: a policy naming the venv's python3 link itself as a readable root is refused naming .venv/bin/python, yet bwrap binding that link mounts its target and the interpreter execs (measured with bwrap directly). link_chain also normalises '..' lexically before following links, so a path like a/link/../b is resolved wrong.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A policy that lacks the interpreter's ELF interpreter or a shared library it needs is refused before bwrap with a typed error naming the path
- [ ] #2 A policy that bwrap can start the supervisor under is not refused
- [ ] #3 link_chain resolves '..' after a link as the kernel does
<!-- AC:END -->
