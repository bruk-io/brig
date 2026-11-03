---
id: TASK-0047
title: >-
  Pre-start OSErrors from files.facts and files.link_chain still escape
  create_bwrap_jail bare
status: To Do
assignee: []
created_date: '2026-11-03T19:22:00Z'
labels:
  - brig
  - errors
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0046's worker, confirmed in review (2026-11-03). src/brig/infra/files.py: facts() catches only FileNotFoundError/NotADirectoryError around os.stat, so a policy path the embedder cannot search (PermissionError) or a symlink loop (ELOOP) crosses create_bwrap_jail as a bare OSError, past the driver-exception-boundary rule. link_chain() calls os.readlink, which can raise if the link changes underneath it (a race). Related: in bwrap._supervisor_path, assemble.assembled_source() runs inside the write's try, so a broken install's read error reads as StateDirectoryWriteFailed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every OSError files.facts and files.link_chain can raise during create_bwrap_jail crosses as one of presentation/errors.py's types, with the OSError as its cause; integration tests pin each; recorded failing before the fix
- [ ] #2 Reading brig's own supervisor source failing is not reported as StateDirectoryWriteFailed
<!-- AC:END -->
