---
id: DRAFT-0027
title: Test seams are public API, and the supervisors seam skips the policy compile
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:58:00Z'
labels:
  - brig
  - api
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: create_bwrap_jail(supervisors=...) skips the compile and reports frozendict(); the bwrap argv lives in LiveSupervisor, not the effect, so a structurally matching port runs the bare command. Rule 4 forces every fake seam into embedder signatures, while files, state_dir, placeholders and assemble have none. Also: Jail keeps the int of a namespace fd destroy_jail closed (a reused number would verify against another jail); destroy_jail takes the default directories port; 57 public names, 19 unrelated error classes, ValueError outside errors.py; no create-and-always-destroy helper; spec/glossary lines that do not match the code (compile_run, grade as only producer). Proposed: the launch argv on the effect (decision-0007 item 6), a host-facts port, a brig.testing entry, a stateful fd handle, a BrigError base.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03 (TASK-0045's review): Jail now holds two raw fd ints that destroy_jail closes, channel_namespace_fd and channel_directory_fd; both want the stateful handle that refuses use after close.
<!-- SECTION:NOTES:END -->
