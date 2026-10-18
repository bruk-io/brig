---
id: TASK-0018
title: >-
  First real CI run found a margin-calculation bug in the forged-done timing
  assertions
status: To Do
assignee:
  - '@claude'
created_date: '2026-10-18 23:30'
labels:
  - brig
dependencies: []
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
First-ever CI run on bruk-io/brig (GitHub Actions, ubuntu-latest) failed on tests/e2e/test_supervisor_link_gateway.py's two forged-done tests: 'done arrived after only 0.40s -- the forged event was trusted', assert 0.395 >= 0.4. Not a security regression: the preceding assert outcome == real_exit_code passed in both cases, so the forged event was genuinely never trusted -- only the auxiliary timing sanity check flaked.

Root cause: a real math bug, not CI slowness. 'start = time.monotonic()' was captured AFTER the first await_done call's own early-check deadline (forge_sleep_s / 4) had already elapsed, but the assertion ('elapsed >= forge_sleep_s - 0.1') was written as if elapsed measured the FULL forge_sleep_s duration from process spawn. The achievable ceiling for elapsed from that start point is forge_sleep_s * 3/4 (0.375s for forge_sleep_s=0.5), already below the asserted 0.4s floor before any CI scheduling variance enters into it -- it only ever passed locally by luck (python startup overhead happening to push the real observed value just over 0.4s).

Fixed: start is now captured before the early-check call (i.e., at the actual process-spawn point), so elapsed genuinely measures the full real process lifetime and the margin means what it says. Verified 5/5 stable on macOS and 5/5 stable on real Linux+bwrap (brig-probe-amd64:latest) after the fix.
<!-- SECTION:DESCRIPTION:END -->
