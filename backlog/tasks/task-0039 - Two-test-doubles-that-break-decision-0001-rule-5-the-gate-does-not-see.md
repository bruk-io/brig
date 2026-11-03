---
id: TASK-0039
title: Two test doubles that break decision-0001 rule 5 the gate does not see
status: To Do
assignee: []
created_date: '2026-11-03T04:14:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/e2e/test_supervisor_assemble.py:120,141 builds fake_sys, a types.SimpleNamespace stand-in for sys, in tests/e2e. Rule 5 says doubles live only in tests/integration/. tests/integration/test_policy_refusal.py:68 assigns directories.create = stop on a FakeChannelDirectories. That is a patch of a method, and FakeChannelDirectories.fail_create already gives the same stop. TASK-0033 flagged both; brig-no-patching sees neither, because it knows a double only by its name and does not track local objects.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The preamble guard is tested without a double in e2e: the version enters as data, or the test moves to tests/integration with a fake
- [ ] #2 test_policy_refusal stops at create through the fake's own fail_create, with no method replaced
<!-- AC:END -->
