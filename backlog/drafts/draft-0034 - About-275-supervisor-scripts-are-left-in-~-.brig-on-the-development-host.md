---
id: DRAFT-0034
title: About 275 supervisor scripts are left in ~/.brig on the development host
status: Draft
assignee: []
created_date: '2026-11-04T15:17:00Z'
labels:
  - brig
  - lifecycle
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen by TASK-0053's worker, 2026-11-04: /root/.brig holds about 275 supervisor scripts, mostly from before that session, a few maybe from test runs it killed. TASK-0001.21 made scripts per-jail and removed at teardown; leftovers mean either killed test processes (no teardown runs, which may be acceptable but should be swept like placeholders) or a teardown path that misses the script. Find which: count scripts before and after a full just done, and after a killed embedder; if brig leaves them, sweep them as the placeholders are swept.
<!-- SECTION:DESCRIPTION:END -->
