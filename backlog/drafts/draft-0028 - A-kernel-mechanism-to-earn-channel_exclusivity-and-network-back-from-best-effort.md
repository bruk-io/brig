---
id: DRAFT-0028
title: >-
  A kernel mechanism to earn channel_exclusivity and network back from
  best-effort
status: Draft
assignee: []
created_date: '2026-11-03T18:00:00Z'
labels:
  - brig
  - grades
  - size-5
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0043 capped channel_exclusivity at BEST_EFFORT whenever a jail sees any host path (any readable or writable root), and network at no stronger than channel_exclusivity, because a Unix socket accepts a connect through a read-only mount and no list of places finds every socket a host keeps (decision-0008, the 2026-11-03 note: ENFORCED needs a kernel mechanism). Every bwrap jail mounts its interpreter, so today neither claim can be ENFORCED.

The question: which kernel mechanism makes "the jail dials no host socket but its declared channels" hold, so a battery can measure it ENFORCED.

What is measured here: this kernel's Landlock is ABI 7 (landlock_create_ruleset with LANDLOCK_CREATE_RULESET_VERSION returns 7). Its LANDLOCK_SCOPE_ABSTRACT_UNIX_SOCKET (ABI 6) scopes abstract sockets only; nothing in ABI 7 restricts connect(2) to a pathname Unix socket, so Landlock cannot hold the claim on this kernel.

The candidate: the supervisor holds each declared channel as a listening fd it was handed before the jail starts (so the command never needs to create or connect a pathname socket to reach a channel), and installs a seccomp filter before exec that refuses socket(AF_UNIX, ...) (and socketpair is harmless: it reaches nothing outside), so the command cannot make a socket to dial with. Open questions for the design: how a command that legitimately makes AF_UNIX sockets (a language server, a test suite, git's fsmonitor) is served, or whether such a policy opts out and keeps BEST_EFFORT; whether connect on an inherited unconnected socket must be filtered too; how the channel endpoints in argv change when the command is handed an fd instead of a path; whether io_uring (IORING_OP_SOCKET) must be refused alongside; and the battery that plants a host socket under a readable root and measures the dial refused, with a positive control that the channel still works.
<!-- SECTION:DESCRIPTION:END -->
