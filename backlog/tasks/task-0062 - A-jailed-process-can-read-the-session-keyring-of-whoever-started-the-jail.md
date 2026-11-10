---
id: TASK-0062
title: A jailed process can read the session keyring of whoever started the jail
status: To Do
assignee: []
created_date: '2026-11-10 17:16'
labels:
  - security
  - size-2
dependencies: []
type: bug
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From bh-02's port onto bruk-io/brig v0.1.0, bh-02 TASK-0219 (high). Measured on the old in-repo brig (bh-02 commit d0c3a416 (its in-repo libs/brig, removed by bh-02's port to this brig)), in a Docker container with seccomp unconfined: the process that started the jail joined a session keyring as a login does and added a key, and a jailed program with namespaces found it and read its payload. One jail or two made no difference, and the old brig's bwrap jail had no seccomp filter. Check this brig: does a jailed process see the starter's session keyring, on a bare Linux host as well as in a container? A likely fix, untried: join a new session keyring (KEYCTL_JOIN_SESSION_KEYRING) per jailed process.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A jailed process cannot read keys in the session keyring of the process that started the jail, shown by a test with a control
- [ ] #2 The measurement says whether a bare Linux host was exposed
<!-- AC:END -->
