---
id: DRAFT-0014
title: >-
  A jail's own resources bypass the effect system: creation and teardown are
  hand-written sequences
status: Draft
assignee: []
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-04T12:40:00Z'
labels:
  - size-5
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. `operations.create`/`destroy` cover only the process. The supervisor script, channel directory, namespace fd and events pipe are acquired in a `try/except BaseException` in `create_bwrap_jail` and released in a fixed sequence in `destroy_jail`; the egress proxy would be a fifth, added by hand to both. Rule 10's reason for effects is uniform treatment, undo order among it. Proposed: acquire/release effects that `create` yields and teardown releases in reverse, and `Jail` as a context manager.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision recorded: whether jail resources become effects, and the order teardown releases them in
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review 2026-11-04: TASK-0044 answered most of it: one dismantle (presentation/jail.py) serves create's failure path and destroy_jail, and the egress proxy rides inside supervisors.close. What remains is a preference (uniform undo order over a six-keyword function); the owner rewrites its why against dismantle or it is archived.
<!-- SECTION:NOTES:END -->
