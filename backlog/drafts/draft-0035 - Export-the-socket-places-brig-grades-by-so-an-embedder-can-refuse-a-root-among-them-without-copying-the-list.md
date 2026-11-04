---
id: DRAFT-0035
title: >-
  Export the socket places brig grades by, so an embedder can refuse a root
  among them without copying the list
status: Draft
assignee: []
created_date: '2026-11-04T17:21:00Z'
labels:
  - brig
  - grades
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-0012 in the embedder (bh-02) asks brig to export SOCKET_DIRECTORIES, or a pure ceilings_for(FsPolicy, egress), so the embedder can predict a grade (refuse a project under /tmp, warn a grant would make network violated) without copying brig's list. bh-02's TASK-0181.02 copies it today (/tmp, /var/tmp, /run, /var/run, /dev/shm, XDG_RUNTIME_DIR), which can drift. Export the tuple (and how XDG_RUNTIME_DIR is added), or a pure function from an FsPolicy and an egress policy to the ceilings a create would report.
<!-- SECTION:DESCRIPTION:END -->
