---
id: DRAFT-0015
title: Mountpoints for absent paths are left on the host after destroy_jail
status: Draft
assignee: []
created_date: '2026-11-02T17:23:00Z'
labels:
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. Measured: a writable project with read-only binds over two absent paths (`.envrc`, `.git/hooks`) and `/dev/null` bound over an absent `secret.env`. After `destroy_jail` the host project held a `.envrc` directory, `.git/` and `.git/hooks` directories and an empty `secret.env` file, none marked as brig's, none removed: bwrap creates a missing mountpoint on the writable source beneath it. A mask over an absent secret plants a file in the embedder's tree. Removing them safely needs to know which brig made and that no other jail still mounts over them (a mark, a record, a per-user lock or brig's verified process identity), which is bwrap knowledge an embedder should not have to carry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After destroy_jail, no mountpoint brig's compile caused to be created on the host remains, and none that existed before is removed
- [ ] #2 An e2e test plants absent write-denied and masked paths under a writable bind and shows the host tree is as it was after teardown, including while a second jail over the same tree still runs
<!-- AC:END -->
