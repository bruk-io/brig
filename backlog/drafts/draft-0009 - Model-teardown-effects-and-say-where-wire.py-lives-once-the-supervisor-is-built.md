---
id: DRAFT-0009
title: >-
  Model teardown -> effects, and say where wire.py lives once the supervisor is
  built
status: Draft
assignee: []
created_date: '2026-10-18 03:11'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two model/text accuracy gaps left by TASK-0001.13.

1) src/brig/domain/teardown.py:38 imports from brig.domain.effects, but docs/architecture/models/brig/_relationships.c4 has no 'teardown -> effects' edge. Every other brig-internal import in src/brig maps to a modeled relationship; this is the only orphan. Domain->domain, so decision-0001 rule 1 is unaffected -- it is an accuracy gap, not a layering violation.

2) docs/architecture/models/brig/supervisor.c4's header comment and the new 'Containers' paragraph in docs/architecture/index.md both attribute 'infra/supervisor/{wire,program,link}.py' to the supervisor container, which contradicts decision-0002's corrected text (link.py runs in the library's own process and stays in the 'library' container). Also unresolved in either place: per decision-0001 rule 17 the dropped PID-1 file is exactly wire.py + program.py, yet link.py is the host's end of the same newline-delimited JSON protocol, so wire.py plausibly has code on both sides of the container boundary. Whoever builds the supervisor should settle that and make the model and index text say the same thing as decision-0002.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 models/brig/_relationships.c4 models teardown -> effects
- [ ] #2 supervisor.c4's comment and docs/architecture/index.md agree with decision-0002 on which files belong to the supervisor container
- [ ] #3 decision-0002 says explicitly whether wire.py is shared by the host end (link.py) or duplicated, consistent with rule 17
<!-- AC:END -->
