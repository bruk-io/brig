---
id: DRAFT-0022
title: Three ceilings claim ENFORCED where only a list of places backs them
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - brig
  - grades
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03. (a) fs_write is ENFORCED with a readable root nested in a writable root; demonstrated: the host renamed W/vendor and made a new one, and the jail then wrote W/vendor/lib.py. ceilings (domain/jail_types/bwrap.py) counts only write_denies and masks; compute it from the mounts (any READ_ONLY under WRITABLE caps it). (b) channel_exclusivity is ENFORCED while the jail reaches a host agent socket outside SOCKET_DIRECTORIES; demonstrated with a gpg-agent socket under a home directory. (c) network stays ENFORCED when a socket the jail can dial gives it the network (reasoned). Principle proposed: a ceiling reaches ENFORCED only when a kernel mechanism holds the claim, never because a path list found nothing.
<!-- SECTION:DESCRIPTION:END -->
