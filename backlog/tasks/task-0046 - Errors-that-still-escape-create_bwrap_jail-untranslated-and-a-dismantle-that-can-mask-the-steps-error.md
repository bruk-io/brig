---
id: TASK-0046
title: >-
  Errors that still escape create_bwrap_jail untranslated, and a dismantle that
  can mask the step's error
status: To Do
assignee: []
created_date: '2026-11-03T18:58:00Z'
updated_date: '2026-11-03T18:59:00Z'
labels:
  - brig
  - errors
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0044/0045's worker and review (2026-11-03): (1) writing the supervisor script (_supervisor_path) and state_dir.ensure_empty can raise a bare OSError out of create_bwrap_jail, past the driver-exception-boundary rule; (2) dismantle's docstring says it raises nothing, but an OSError from run(operations.destroy) or supervisors.close would escape and hide the failed step's own error; (3) if run(operations.create) itself raises after bwrap has spawned, process is still None and the kill ladder is skipped (true before TASK-0044 too).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every OSError create_bwrap_jail can raise before the start (writing the supervisor script, preparing the state directory) crosses as one of presentation/errors.py's types, with the OSError as its cause; integration tests with fakes pin each; recorded failing before the fix
- [ ] #2 dismantle never hides the failed step's error: a teardown or close failure inside it is attached to the step's error (add_note or a chained cause) or raises JailTeardownFailed, and its docstring says which
- [ ] #3 If operations.create raises after bwrap has spawned, the spawned process is still torn down (the create effect hands back what it spawned, or the driver reaps by pidfd); a test with a fake that spawns then fails pins it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
