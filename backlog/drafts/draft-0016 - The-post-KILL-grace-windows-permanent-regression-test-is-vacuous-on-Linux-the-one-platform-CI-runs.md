---
id: DRAFT-0016
title: >-
  The post-KILL grace window's permanent regression test is vacuous on Linux,
  the one platform CI runs
status: Draft
assignee: []
created_date: '2026-10-18 20:05'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0001.07's fix (destroy_jail's kill_grace_s, bounding the post-KILL Verify's group-liveness poll) is pinned by tests/e2e/test_processes_gateway.py's test_destroy_jail_survives_the_leader_exiting_before_its_group, which now asserts teardown_failed == 0 over 150 iterations. That loop sleeps 0.05s between spawn and destroy_jail.

Measured by the reviewer against the landed code, same reproduction argv (/bin/sh -c "trap '' TERM; sleep 30 & exit 0"), real destroy_jail:

- macOS, 0.05s pre-sleep (the test's own shape): 145/150 JailTeardownFailed at kill_grace_s=0.0, 0/150 at the default. The test genuinely pins the fix here.
- brig-probe-amd64:latest (privileged), 0.05s pre-sleep: 0/150 at kill_grace_s=0.0 AND 0/150 at the default. The test passes identically with the grace window removed -- it proves nothing about TASK-0001.07 on Linux.
- brig-probe-amd64:latest, NO pre-sleep (otherwise identical): 200/200 JailTeardownFailed at kill_grace_s=0.0, 0/200 at the default. The race is real and decisive on Linux -- the pre-sleep is what hides it, because by then the leader has already exited and the sibling has settled.

CI runs Linux, so the regression this test exists to catch would reappear there unseen. The fix looks like one line: drop or shorten the pre-sleep (or add a second, no-pre-sleep loop), re-measuring both platforms to confirm the shape still reproduces where it is supposed to.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A permanent e2e test fails on Linux when destroy_jail's post-KILL grace window is disabled (kill_grace_s=0.0), measured in brig-probe-amd64:latest
- [ ] #2 The same test still passes, on both macOS and Linux, against the landed grace window
<!-- AC:END -->
