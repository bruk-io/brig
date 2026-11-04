---
id: TASK-0052
title: >-
  A policy without the interpreter's ELF loader and libraries passes
  interpreter_refusal and fails in bwrap with execvp No such file
status: To Do
assignee: []
created_date: '2026-11-03T03:46:00Z'
updated_date: '2026-11-04T12:40:00Z'
labels:
  - brig
  - fs-policy
  - size-2
  - finish-moved
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
- [ ] #4 infra.files.link_chain resolves a/link/../b as the kernel does (the link first, then ..), not by normalising .. as text; a tmp-tree test pins it; repro test recorded failing
- [ ] #5 A policy whose readable root is the venv's python3 link itself is not refused by interpreter_refusal
- [ ] #6 The ELF loader and DT_NEEDED half is split out as a design draft of its own
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
