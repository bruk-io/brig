---
id: DRAFT-0008
title: >-
  Mechanize the driver-exception-boundary rule as a pypeeker rule, not just a
  markdown reminder
status: Draft
assignee: []
created_date: '2026-10-18 02:21'
labels:
  - brig
  - tooling
dependencies: []
parent_task_id: TASK-0001
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

TASK-0001.08's own Implementation Notes (carried over from an earlier session) name this directly: this same class of bug -- a raw infra exception escaping the public API through an unwrapped driver call -- was found independently in two separate adversarial reviews (TASK-0001.03, TASK-0001.06), and fixed a third time by TASK-0001.08 itself (group_alive/signal_group's PermissionError). Each time the cause was the same shape: a *new* effect or call site into infra was added to presentation/drivers/bwrap.py without wrapping it, not that decision-0001 rule 13 or .claude/rules/driver-exception-boundary.md's reminder were unknown.

A standing rule a reviewer has to remember to re-check by hand, three times over, is exactly the gap decision-0001's own philosophy argues against: 'every boundary in the layout is a pypeeker rule, so a change that crosses one fails just done, not a review' (decision-0001, Consequences). This boundary is currently enforced only by review and a markdown reminder, not mechanically.

## Open questions

- [ ] What is the actual rule shape: every call from a driver module into brig.infra.* must be lexically inside a try/except that narrows OSError (or a named infra exception) to one of presentation/errors.py's types -- is that expressible as a pypeeker custom DSL rule (ast-shape over presentation/drivers/*.py), or does it need pypeeker's heuristic engine instead?
- [ ] Scope: every presentation/drivers/<type>.py module (bwrap today; seatbelt, oci later -- decision-0001 rule 3 makes each a slice), or just bwrap.py until a second jail type exists to generalize from?
- [ ] False positives: does the rule need to understand that spawn's SpawnError is already a non-exception-raising... (infra never raises brig types, rule 9) -- i.e. what should the rule flag as 'unwrapped' once infra itself stops raising for a given call (as TASK-0001.08 just did for group_alive/signal_group), versus calls that still can raise (spawn)?
- [ ] Is this pypeeker-rules/brig.py's job (same place brig-layers, brig-slices etc. live), or does it belong upstream in pypeeker itself as a reusable heuristic (a driver/adapter boundary pattern other projects would also want)?
<!-- SECTION:DESCRIPTION:END -->
