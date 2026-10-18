---
id: TASK-0013
title: 'Restructure reap/teardown for verified process identity, per decision-0003'
status: To Do
assignee: []
created_date: '2026-10-18 19:06'
updated_date: '2026-10-18 19:07'
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
- [ ] #2 A per-member group-liveness probe replaces or extends group_alive so a deliberately-held pid reads correctly on both platforms: measured directly against real bwrap on Linux (a /proc-based enumeration excluding the known-held pid is the named candidate) and re-measured on macOS for the mixed case decision-0003 did not test (a held zombie leader plus another genuinely-alive group member) -- not assumed from today's single-process-group measurement
- [ ] #3 TASK-0001.08's group_alive docstring's 'the group is gone either way' reasoning is corrected to state the real, now-measured exception (a deliberately-held pid is not 'gone', and must not read as gone)
- [ ] #4 Landed with or after TASK-0001.07 (bounded grace period for multi-process groups), not independently -- TASK-0001.07 is specified against today's Verify/group_alive semantics and this task changes that premise
- [ ] #5 Every test decision-0003 named as contradicted (not just broken) by this change is rewritten, not patched: tests/unit/test_teardown.py's exact-effect-sequence assertions, tests/integration/test_teardown_leader_reaped_early.py's reaped/checked assertions, tests/integration/test_walking_skeleton.py's reaped == [] assertion, tests/e2e/test_processes_gateway.py's direct reap(pid) == ProcessUnknown() assertions
- [ ] #6 Full regression: just done green, and the existing walking-skeleton and teardown batteries pass for real against bwrap on Linux as well as macOS -- the platform divergence this decision found was invisible on macOS alone
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
finish-moved: created without acceptance criteria (a tool-sequencing artifact -- task create then a follow-up edit added them), then given its real ACs in the very next edit, drawn directly from decision-0003's own Consequences section. No scope added beyond what the decision already named; this is the task's first real shape, not a later narrowing or widening.
<!-- SECTION:NOTES:END -->
