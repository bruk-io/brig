---
id: TASK-0013
title: 'Restructure reap/teardown for verified process identity, per decision-0003'
status: To Do
assignee: []
created_date: '2026-10-18 19:06'
updated_date: '2026-10-18 19:10'
labels:
  - size-8
  - finish-moved
dependencies: []
references:
  - >-
    backlog/decisions/decision-0003 -
    Verified-process-identity-across-reap-and-teardown-peek-before-reap-no-pidfd-no-per-platform-split.md
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-0003 chose peek-before-reap (os.waitid WNOWAIT) over pidfd to close the raw pid-reuse hazard DRAFT-0003/TASK-0001.23 flagged, but its own measurement found a real, previously-unknown platform divergence: group_alive() answers True on Linux and False on macOS for the identical case of a deliberately-held (peeked, not reaped) zombie leader with nothing else in its group. This task is the actual restructuring the decision named as real, unsolved scope -- not a mechanical swap.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 infra/processes.py's reap/reap_deadline/reap_nowait peek (WNOWAIT) rather than reap unconditionally; the real reap happens only once teardown's own ladder is done with that pid, via a new, explicit terminal release step (not hidden module state, not a change to effects.py's closed Effect union without updating every assert_never match site)
- [ ] #2 A new per-member group-liveness mechanism for Linux only: killpg there answers 'exists' identically for a zombie-only group and a genuinely-alive one, with no distinction -- a /proc-based enumeration excluding the known-held pid(s) is the named candidate, measured directly against real bwrap in brig-probe-amd64:latest for both the single-held-leader and the mixed (held leader + genuinely-alive sibling) cases. macOS's group_alive needs no change (confirmed: killpg's EPERM there already distinguishes 'entirely gone' from 'something still alive' correctly in both cases, verified empirically against the real function).
- [ ] #3 TASK-0001.08's group_alive docstring's 'the group is gone either way' reasoning is corrected to state the real, now-measured exception (a deliberately-held pid is not 'gone' on Linux, and must not read as gone there)
- [ ] #4 Landed with or after TASK-0001.07 (bounded grace period for multi-process groups), not independently -- TASK-0001.07 is specified against today's Verify/group_alive semantics and this task changes that premise
- [ ] #5 Every test decision-0003 named as contradicted (not just broken) by this change is rewritten, not patched: tests/unit/test_teardown.py's exact-effect-sequence assertions, tests/integration/test_teardown_leader_reaped_early.py's reaped/checked assertions, tests/integration/test_walking_skeleton.py's reaped == [] assertion, tests/e2e/test_processes_gateway.py's direct reap(pid) == ProcessUnknown() assertions
- [ ] #6 Full regression: just done green, and the existing walking-skeleton and teardown batteries pass for real against bwrap on Linux as well as macOS -- the platform divergence this decision found was invisible on macOS alone
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
finish-moved: created without acceptance criteria (a tool-sequencing artifact -- task create then a follow-up edit added them), then given its real ACs in the very next edit, drawn directly from decision-0003's own Consequences section. No scope added beyond what the decision already named; this is the task's first real shape, not a later narrowing or widening.

finish-moved: AC#2 narrowed from 'both platforms, mixed case unverified on either' to 'Linux only' after directly measuring the mixed case (held zombie leader + genuinely-alive backgrounded sibling) against the real macOS group_alive: it already answers True correctly, no redesign needed there. This is the decision-0003 amendment recorded the same day, carried into this task's own ACs rather than left stale.
<!-- SECTION:NOTES:END -->
