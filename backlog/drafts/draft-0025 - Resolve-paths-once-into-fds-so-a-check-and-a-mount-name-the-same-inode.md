---
id: DRAFT-0025
title: Resolve paths once into fds so a check and a mount name the same inode
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - brig
  - fs-policy
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: the rename and link bugs (TASK-0001.31, .33, .34, ThroughLink) share one cause: files.facts checks by path, placeholders.hold acts by path through parents, and bwrap resolves every mount again by path; the sweep is the same shape. Proposed: open each root and each entry beneath it with openat2(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS), take facts from fstat, make placeholders with mkdirat, pass fds to bwrap with --bind-fd/--ro-bind-fd (present in 0.9.0), and use --info-fd for the PID 1 instead of the /proc scan. Also: refuse a state directory inside or reached through any writable root (it holds the supervisor scripts and placeholder records). A design question for a decision record.
<!-- SECTION:DESCRIPTION:END -->
