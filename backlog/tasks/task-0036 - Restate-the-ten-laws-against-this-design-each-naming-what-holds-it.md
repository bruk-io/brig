---
id: TASK-0036
title: Restate the ten laws against this design, each naming what holds it
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T04:07:00Z'
updated_date: '2026-11-03T04:08:00Z'
labels:
  - size-2
dependencies: []
type: task
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0001's notes (architecture review, 2026-11-02): the ten laws are carried verbatim from the old SPEC and still name things cut or never built here (law 2's mechanism/stack/launcher, law 7's Process.stop/control, law 9's EnvPolicy.set, laws 5-6's inbound messages and provenance), so criterion #17's tests could not mean anything yet. Restate each in this design's terms, keeping its number and intent, and say which code and which test holds it, or that none does yet.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of the ten laws names only things that exist in brig (or says plainly it binds future work), and keeps its old SPEC intent
- [ ] #2 Each law says which test holds it now, or that none does yet, so TASK-0001 #17's remaining work is visible
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker's report (Claude): 168a633. docs/spec/index.md's ten laws restated. What each names now: 1 the report's ceilings (decision-0008); 2 brig's refusals; 3 FsPolicy intent compiled per jail type (decision-0007); 4 channels (no observation surface today); 5 channels and the egress relay to come; 6 the supervisor's events, unreachable from the command (decision-0006); 7 interrupt_jail and destroy_jail; 8 grades from batteries, not events; 9 channel_exclusivity incl. socket places, and argv as a shared medium; 10 batteries and failing-test-first. Remaining for TASK-0001 #17: tests for laws 4 and 5 once something exists to hold them, law 3 across a second jail type, and a battery planting survivors for law 7. uv run just docs passes.
<!-- SECTION:NOTES:END -->
