---
id: TASK-0006
title: >-
  The supervisor's temp script lives in /tmp, so any fs policy that excludes
  /tmp breaks every jail under it
status: To Do
assignee: []
created_date: '2026-10-18 13:05'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while reviewing TASK-0001.20 (a dev-dependency change that could not have caused it; confirmed pre-existing against a clean git baseline).

tests/e2e/test_fs_policy_battery.py::test_a_path_outside_the_policy_is_unreadable_in_a_real_bwrap_jail fails DETERMINISTICALLY on real Linux (ubuntu:24.04 amd64, --privileged): 5 runs out of 5, identical node id. 3 runs with TASK-0001.20's diff applied, 2 runs with pyproject.toml/uv.lock reverted to the committed baseline. Same failure both arms, so it is pre-existing and unrelated to that task.

This is NOT container flakiness, NOT a reap race, and NOT related to bwrap-in-container or posix_spawn/setsid (TASK-0001.20's implementation notes characterised it that way; that characterisation is wrong on every count and is corrected here).

Root cause: presentation/api.py:108 writes the assembled supervisor to a tempfile.NamedTemporaryFile with prefix 'brig-supervisor-' -- i.e. into /tmp. The test deliberately builds a policy via _mirror_policy_excluding('tmp') to prove a path outside the allow-list is ENOENT inside the jail. That policy also unbinds the supervisor's own script, so the jail's PID 1 never starts:

  /work/.venv/bin/python: can't open file '/tmp/brig-supervisor-XXXX.py': [Errno 2] No such file or directory

which surfaces as ExitCodeUnknown -> JailExitUnknown(Process(pid=..., pgid=...)) from api.py:331, instead of the expected probe exit code 2.

So the supervisor mechanism (TASK-0001.15 / TASK-0004) has an undeclared dependency on /tmp being bound, which TASK-0001.16's narrowed-policy feature can silently revoke. Any embedder passing a policy that does not bind /tmp gets a jail that cannot start at all.

Invisible on macOS: the test is skipif(shutil.which('bwrap') is None), so it skips there and the whole suite looks green. It would fail on the first real CI run on Linux.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The supervisor's script is reachable from inside the jail regardless of the caller's fs policy (e.g. the supervisor's own path is bound into the launch unconditionally, or the script is passed by a mechanism that does not depend on the policy's binds)
- [ ] #2 tests/e2e/test_fs_policy_battery.py::test_a_path_outside_the_policy_is_unreadable_in_a_real_bwrap_jail passes on real Linux, exiting 2 (ENOENT for the planted secret) rather than raising JailExitUnknown
- [ ] #3 A policy that excludes /tmp is covered by a test asserting the jail still starts, so this coupling cannot regress silently
<!-- AC:END -->
