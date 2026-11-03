---
id: DRAFT-0021
title: >-
  compile_mounts keeps an absent deny or mask that sits under a read-only root
  nested in a writable one, which bwrap cannot mount
status: Draft
assignee: []
created_date: '2026-11-03T03:06:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0024.01 (c4ef292). _kept() keeps an absent deny/mask when any writable root covers it, but decision-0007 item 4's own reason for dropping absent entries is that bwrap cannot make a mountpoint on a read-only mount. With writable=(/w,), readable=(/w/ro,) (or write_denies=(/w/d,)) and an absent mask or deny at /w/ro/x, the most specific covering root is read-only, the entry is kept, and bwrap must mkdir /w/ro/x inside a read-only bind, so the jail fails to start (fails closed, as JailExitUnknown). Related refusal gap: a readable or writable root that does not exist on the host is not refused and reaches bwrap as a missing source.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An absent entry is kept only when the most specific root or deny covering it is writable, with a unit case for a readable root and a write deny nested in a writable root
- [ ] #2 A root absent on the host is refused before anything is created, or the decision says why it is compiled
<!-- AC:END -->
