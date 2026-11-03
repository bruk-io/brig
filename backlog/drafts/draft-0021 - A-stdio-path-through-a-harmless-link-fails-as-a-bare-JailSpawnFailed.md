---
id: DRAFT-0021
title: A stdio path through a harmless link fails as a bare JailSpawnFailed
status: Draft
assignee: []
created_date: '2026-11-03T03:59:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0031 (8b42a6a). _open_through_no_link refuses a link anywhere on a stdio path, including one outside every writable root that no jail can change (a symlinked home, /var/run -> /run). Measured: stdout=D/ln/out.txt with D/ln -> D/real and the writable root elsewhere: create_bwrap_jail raises JailSpawnFailed('could not spawn jail process: ...') caused by NotADirectoryError, which names neither the path nor the link nor what to do.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A stdio path whose lookup passes through a link is refused at create with an error that names the path and the link and says to give the resolved path, or is opened through a link no jail can write
<!-- AC:END -->
