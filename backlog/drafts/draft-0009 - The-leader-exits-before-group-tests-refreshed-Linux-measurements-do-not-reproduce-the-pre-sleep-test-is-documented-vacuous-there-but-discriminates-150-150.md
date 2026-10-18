---
id: DRAFT-0009
title: >-
  The leader-exits-before-group tests' refreshed Linux measurements do not
  reproduce -- the pre-sleep test is documented vacuous there but discriminates
  150/150
status: Draft
assignee: []
created_date: '2026-10-18 22:30'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0017 refreshed the docstrings on tests/e2e/test_processes_gateway.py's two test_destroy_jail_survives_the_leader_exiting_before_its_group tests. The load-bearing Linux figure in them does not reproduce.

Both docstrings tell a reader that the ORIGINAL pre-sleep test proves nothing on Linux: 'by 0.05s the leader has already exited and its orphaned sibling has already settled, so the race this test exists to catch never fires: measured at 0/150 JailTeardownFailed with kill_grace_s=0.0 there, identical to the real default. CI runs Linux, so this test alone would not catch a regression of TASK-0001.07's fix.' The no-pre-sleep variant's docstring repeats the same premise as its reason to exist.

Re-measured by the reviewer, twice, in the named image (brig-probe-amd64:latest, privileged, --platform linux/amd64), forcing the grace window off via brig.destroy_jail.__kwdefaults__['kill_grace_s']=0.0 and running the test unmodified: the pre-sleep test failed 150/150, not 0/150. It is the strongest discriminator measured on either platform. The claim in the docstring is the opposite of what the image does.

Why it matters beyond the arithmetic: the docstrings are the only record of which of these two tests catches a TASK-0001.07 regression on the platform CI runs. A maintainer trimming e2e runtime and trusting them would delete the pre-sleep test as dead weight on Linux -- when measured, it is the one that fires hardest there.

Two smaller drifts in the same docstrings, found alongside: the pre-sleep test's docstring says macOS measured 149/150 at kill_grace_s=0.0 (the task description records 145/150; the reviewer measured 150/150), and the no-pre-sleep test's says macOS noise runs '~2% to ~23%' where the implementer reported 2-34% (the reviewer measured 2/40). The macOS figures are directionally right -- strong pin with the pre-sleep, weak and noisy without -- so only the Linux claim is contradicted.

Neither TASK-0016 nor TASK-0017's acceptance criteria are affected: the no-pre-sleep test is decisive on Linux (39/40 with the grace window disabled) and both tests pass against the real default on both platforms. This is a documentation-versus-evidence defect in the docstrings, not a defect in the tests.

Note for whoever picks this up: the reviewer's host runs the amd64 image emulated on Darwin 27, and scheduling under emulation may not be the environment the original 0/150 was taken in. The fix is probably not to swap one number for another but to make each figure carry the host and method that produced it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The docstrings on both test_destroy_jail_survives_the_leader_exiting_before_its_group tests state only Linux measurements that reproduce in brig-probe-amd64:latest, or name the host and method each figure was taken on
- [ ] #2 Whichever of the two tests actually discriminates on Linux is identified correctly, so a maintainer trimming the suite cannot delete the wrong one on the docstring's say-so
<!-- AC:END -->
