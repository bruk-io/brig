---
id: DRAFT-0026
title: The shared presentation is bwrap-shaped, so a second jail type must edit it
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T12:40:00Z'
labels:
  - brig
  - layout
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: presentation/jail.py types Jail.mounts as bwrap.Mount; api.interrupt_jail signals a Linux PID 1; api.destroy_jail releases bwrap's placeholders; readiness and channel_namespace_fd assume a PID namespace (decision-0005 item 7 says Seatbelt has none); ports.ChannelJailFinished names create_bwrap_jail; __init__ exports bwrap claims unqualified. brig-slices only checks slice-to-slice imports. Proposed: a type-neutral Jail plus a per-type handle Protocol (interrupt, release, readiness) each driver supplies; brig-slices lets only brig/__init__ import jail_types.* or drivers.*; per-type names under brig.bwrap.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design review 2026-11-04: not decidable yet; decisions 0005 item 7 and 0007 item 6 leave Seatbelt's readiness and PID-1 model unmeasured, so a handle Protocol now is built from one example. Do now (size 2): extend brig-slices so shared presentation may not import jail_types.* (planted test), move claim names to domain/claims.py, reword the bwrap-naming docstrings. The handle (a neutral Jail plus interrupt/release/readiness as frozen dataclasses of closures, size 3) after DRAFT-0025's info-fd and DRAFT-0027's seam move.
<!-- SECTION:NOTES:END -->
