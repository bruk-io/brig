---
id: TASK-0002
title: >-
  Nothing enforces decision-0001 rule 7's 'a class holding changing state only
  in infra/'
status: In Progress
assignee:
  - '@bruk'
created_date: '2026-10-17 22:57'
updated_date: '2026-10-18 03:51'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - pypeeker_rules/brig.py
parent_task_id: TASK-0001
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0001.04 closed the brig-class-forms gaps for the inheritance restriction (a new 'brig-class-forms-disallowed-base' trait provider in pypeeker_rules/brig.py) and for the @dataclass frozen=True check. Rule 7 has a third clause -- 'A class holding changing state only in infra/, its invariant in its docstring' -- which TASK-0001.04's description named as part of the brig-class-forms gap but its AC#1 wording did not cover, so it closed neither enforced nor recorded. A bare 'class Foo:' that bundles mutable state, anywhere under src/brig/domain or src/brig/presentation, passes 'just gates' today. Evidence: pypeeker_rules/brig.py _declares_disallowed_base only inspects declared bases; _non_frozen_dataclasses only inspects @dataclass decorators; no rule part looks at a class's file_path for statefulness.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Either brig-class-forms rejects a stateful class outside infra/, with a planted-violation test, or a decision record says why that clause of rule 7 stays a review-time concern
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Investigate whether pypeeker's current DSL can express "a class with instance state
   (assigns to self in __init__) outside src/brig/infra/" -- check columns.py/universes.py
   directly, do not assume from the earlier class-forms work's own limitations (that was about
   base-class facts specifically, a different question).
2. If yes: add the check to brig-class-forms with a planted-violation test. If no: a decision
   record saying why, same pattern as the earlier partial gaps.

### Proof
- just gates, just done green; either a real new finding on a planted violation, or a decision
  record.

### Risks
- "Instance state" needs a real, checkable definition (e.g. any assignment to self.<name>
  inside __init__ outside a frozen dataclass) -- vague enough to false-positive on edge cases
  if not scoped carefully; verify against brig's own existing classes before trusting the rule.
<!-- SECTION:PLAN:END -->
