---
id: TASK-0043
title: Three ceilings claim ENFORCED where only a list of places backs them
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T17:50:00Z'
labels:
  - brig
  - grades
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03. (a) fs_write is ENFORCED with a readable root nested in a writable root; demonstrated: the host renamed W/vendor and made a new one, and the jail then wrote W/vendor/lib.py. ceilings (domain/jail_types/bwrap.py) counts only write_denies and masks; compute it from the mounts (any READ_ONLY under WRITABLE caps it). (b) channel_exclusivity is ENFORCED while the jail reaches a host agent socket outside SOCKET_DIRECTORIES; demonstrated with a gpg-agent socket under a home directory. (c) network stays ENFORCED when a socket the jail can dial gives it the network (reasoned). Principle proposed: a ceiling reaches ENFORCED only when a kernel mechanism holds the claim, never because a path list found nothing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 fs_write's ceiling is computed from the compiled mounts: any read-only mount beneath a writable one (a deny, a mask, a nested readable root) caps it at BEST_EFFORT; e2e: the host replaces a nested readable root and the jail writes into it, and the ceiling it reported allowed for that
- [ ] #2 channel_exclusivity is at most BEST_EFFORT whenever the jail sees any host path a socket could sit in beyond its own channel directory (a list of places is not a mechanism); VIOLATED stays for a visible SOCKET_DIRECTORIES entry or a writable shared root; e2e plants a socket outside the listed places and dials it
- [ ] #3 network is never stronger than channel_exclusivity, since a dialable host socket can carry the network; a unit test pins the ordering
- [ ] #4 decision-0008 is amended (a dated note) with the rule that ENFORCED needs a kernel mechanism, and a draft names the mechanism that could earn channel_exclusivity and network back (Landlock here is ABI 7: abstract sockets only; a supervisor-held listening fd plus a seccomp filter on socket(AF_UNIX) is the candidate)
<!-- AC:END -->
