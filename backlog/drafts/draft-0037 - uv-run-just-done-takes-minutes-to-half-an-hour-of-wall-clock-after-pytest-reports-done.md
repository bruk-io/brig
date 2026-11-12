---
id: DRAFT-0037
title: >-
  uv run just done takes minutes to half an hour of wall clock after pytest
  reports done
status: Draft
assignee: []
created_date: '2026-11-12 13:02'
updated_date: '2026-11-12 13:22'
labels:
  - test-hygiene
  - darwin
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0063's review (2026-11-12). On this Mac, 'uv run just done' took 33 min wall clock against about 32 s of CPU, and its e2e step 1945 s against the 54 s pytest reported.

Measured (macOS 27.0.1, branch egress-port):
- Full e2e suite with output to a file: pytest reports 53.7 s, wall clock 537 s.
- Per file, stdout to a file and stderr captured by a shell pipe: only tests/e2e/test_processes_gateway.py shows the gap, 13.60 s reported against 942 s wall. Every seatbelt e2e file and test_supervisor_link_gateway.py exit within a second of their summary.
- The same file with stdout and stderr both to a file exited at once, twice.
- During the gap the pytest process itself stays alive (not some other process holding the pipe). sample shows it in os_waitpid and __semwait_signal, and a defunct child about 1 s old keeps reappearing under it, so something keeps spawning and reaping after the session summary.
- Not yet known: which test or teardown does it; whether main (before TASK-0061) has it. The file is from main: test_destroy_jail_survives_the_leader_exiting_before_its_group (11.4 s) is the slowest in it.

Next step: run test_processes_gateway.py with stderr on a pipe under PYTHONFAULTHANDLER and send SIGABRT during the gap to get the Python stack; bisect by test with -k.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Intermittent: on the same branch, after 9068f9a, uv run just done took 94 s wall clock and uv run just test-e2e 62 s (pytest reported 61.9 s), with no gap. Earlier runs of that day took 33 min, 942 s for test_processes_gateway.py alone, and 537 s for the e2e suite to a file. So the cause depends on something outside the tests' own timing, and a reproduction should loop the file until the gap appears.
<!-- SECTION:NOTES:END -->
