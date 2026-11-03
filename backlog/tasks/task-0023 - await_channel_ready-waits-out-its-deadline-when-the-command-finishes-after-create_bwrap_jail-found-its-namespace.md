---
id: TASK-0023
title: >-
  await_channel_ready waits out its deadline when the command finishes after
  create_bwrap_jail found its namespace
status: To Do
assignee:
  - '@claude'
created_date: '2026-11-03T02:42:00Z'
labels:
  - size-2
dependencies: []
type: bug
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0022, 2026-11-03. tests/e2e/test_channel_jail_finished.py's first test assumes `true` finishes before `create_bwrap_jail`'s namespace scan finds the jail's PID 1 (TASK-0001.30). When the scan wins instead, `channel_namespace_fd` is set, the command then exits, and `await_channel_ready` polls an empty channel until `timeout_s` and answers `ChannelNotReady`, never `ChannelJailFinished`. Measured at 739dd94 with no change: 1 run in 3 failed, after 10.22s (the test's deadline). TASK-0022's supervisor does more before starting its command (it makes itself non-dumpable), so the scan wins every time and the test fails 5 in 5. The property the test names (a jail whose command finished reads as finished, at once) does not depend on which side of the race the scan landed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 await_channel_ready answers ChannelJailFinished as soon as the jail's own process has exited, whether or not create_bwrap_jail held its namespace, and never reaps it (decision-0003: peek, not reap)
- [ ] #2 test_channel_jail_finished.py asserts that property and its timing, not which side of the scan's race it landed on, and passes 10 runs in 10 with TASK-0022's supervisor
<!-- AC:END -->
