---
id: TASK-0010
title: >-
  Model teardown -> effects, and say where wire.py lives once the supervisor is
  built
status: To Do
assignee: []
created_date: '2026-10-18 03:11'
updated_date: '2026-10-18 04:34'
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
- [x] #1 models/brig/_relationships.c4 models teardown -> effects
- [x] #2 supervisor.c4's comment and docs/architecture/index.md agree with decision-0002 on which files belong to the supervisor container
- [x] #3 decision-0002 says explicitly whether wire.py is shared by the host end (link.py) or duplicated, consistent with rule 17
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC#1/#2 resolved directly: added the teardown -> effects edge, and synced
supervisor.c4/docs/architecture/index.md to decision-0002's corrected wording.

AC#3, settled empirically in TASK-0001.15 step 3 (link.py): wire.py's message
format is shared, not duplicated, across the host/jail boundary -- but only on
the host side. infra/supervisor/link.py (the host's end, never crossing into
the jail) imports wire.py directly -- `from brig.infra.supervisor import wire`,
then `wire.encode_exec_request`/`wire.decode_event` -- and that import costs
nothing: both modules are stdlib-only and same-package, so there is no
resolution problem on this side of the boundary at all. Confirmed by running
`just gates` (pypeeker's rule 6 checks, `over-exposed-module-symbol` and
`under-exposed-access`, both pass once the three names link.py's own code
calls -- `Event`, `encode_exec_request`, `decode_event` -- dropped their
leading underscore) and by a manual end-to-end run of link.py's `_start` +
`read_event` against the real program.py over real OS pipes, which round-
tripped a started/exited/done sequence correctly.

program.py (the jail side) still duplicates wire.py's encode/decode rather
than importing it, and that duplication is correct, not something this
settles differently: once wire.py and program.py assemble into the one
stdlib-only file dropped as PID 1 inside the jail (rule 17), there is no
installed `brig` package there for an `import brig.infra.supervisor.wire` to
resolve against, and a bare `import wire` is not a form this file's own
location as a module inside the `brig.infra.supervisor` package can produce
during ordinary development/type-checking/pypeeker-check. So the answer is not
"shared" or "duplicated" as a single, whole-protocol choice -- it is both,
split exactly at the boundary DRAFT-0009 itself asked about: shared by import
on the host side (link.py), duplicated by convention on the jail side
(program.py), with the two kept in agreement by matching literal `kind`/field
names rather than a shared import, and pinned by whatever test a later step
of TASK-0001.15 adds.
<!-- SECTION:NOTES:END -->
