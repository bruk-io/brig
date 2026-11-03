---
id: TASK-0044
title: A failed create_bwrap_jail leaves a running jail nothing can destroy
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:31:00Z'
labels:
  - brig
  - lifecycle
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (reasoned from code): in presentation/drivers/bwrap.py, once run(operations.create...) started the supervisor, _placeholders.attach or _namespace_fd_for can still raise (ChannelNamespaceNotFound is documented 'with process still running'). The except path unlinks the script, removes the channel directory and releases placeholders while the jail still mounts over them, and never tears the process down; the embedder gets no Jail to destroy. Proposed: once a process exists, the failure path runs operations.destroy and releases placeholders only on GONE; share one cleanup with destroy_jail.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Once the supervisor process exists, every failure inside create_bwrap_jail tears the jail down through the same destroy path destroy_jail uses, and releases placeholders only once teardown reports the process gone
- [ ] #2 An integration test with fakes fails each step after the start (placeholder attach, the namespace scan) and asserts the process was destroyed and nothing was released while it lived; recorded failing before the fix
- [ ] #3 create_bwrap_jail and destroy_jail share one cleanup function, so the two paths cannot disagree again
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
