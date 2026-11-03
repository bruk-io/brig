---
id: TASK-0046
title: >-
  Errors that still escape create_bwrap_jail untranslated, and a dismantle that
  can mask the step's error
status: To Do
assignee: []
created_date: '2026-11-03T18:58:00Z'
labels:
  - brig
  - errors
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0044/0045's worker and review (2026-11-03): (1) writing the supervisor script (_supervisor_path) and state_dir.ensure_empty can raise a bare OSError out of create_bwrap_jail, past the driver-exception-boundary rule; (2) dismantle's docstring says it raises nothing, but an OSError from run(operations.destroy) or supervisors.close would escape and hide the failed step's own error; (3) if run(operations.create) itself raises after bwrap has spawned, process is still None and the kill ladder is skipped (true before TASK-0044 too).
<!-- SECTION:DESCRIPTION:END -->
