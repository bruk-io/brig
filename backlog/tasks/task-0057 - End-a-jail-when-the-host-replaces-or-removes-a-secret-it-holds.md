---
id: TASK-0057
title: End a jail when the host replaces or removes a secret it holds
status: To Do
assignee: []
created_date: '2026-11-10 17:16'
labels:
  - security
  - size-3
dependencies: []
type: task
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From bh-02's port onto bruk-io/brig v0.1.0: the old in-repo brig had a mount tripwire and this brig has none (no 'tripwire' in src at v0.1.0). In the old brig (bh-02 commit d0c3a416 (its in-repo libs/brig, removed by bh-02's port to this brig); bh-02's runner used it in runner_cordis_plugin/jail.py, and test_runner_confined.py test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds), a jail that held a file the host then replaced or removed was ended with a kill that did not depend on the event loop (Jail.destroy(grace=0) plus a plain killpg fallback, brig decision-193), so a jailed program never read the new contents. A review of bh-02 TASK-0211 suggested the first jail may briefly read the new secret in the window after the rename, which was never confirmed: measure that window here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A jail holding a file ends when the host replaces or removes it, by a kill independent of the event loop, shown by a test
- [ ] #2 Whether a jailed program can read the replacement in the window is measured and stated
<!-- AC:END -->
