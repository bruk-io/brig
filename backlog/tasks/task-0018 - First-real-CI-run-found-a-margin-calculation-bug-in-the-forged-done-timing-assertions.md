---
id: TASK-0018
title: >-
  First real CI run found a margin-calculation bug in the forged-done timing
  assertions
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 23:30'
updated_date: '2026-10-18 23:35'
labels:
  - size-1
dependencies: []
modified_files:
  - tests/e2e/test_supervisor_link_gateway.py
type: bug
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
First-ever CI run on bruk-io/brig (GitHub Actions, ubuntu-latest) failed on tests/e2e/test_supervisor_link_gateway.py's two forged-done tests: 'done arrived after only 0.40s -- the forged event was trusted', assert 0.395 >= 0.4. Not a security regression: the preceding assert outcome == real_exit_code passed in both cases, so the forged event was genuinely never trusted -- only the auxiliary timing sanity check flaked.

Root cause: a real math bug, not CI slowness. 'start = time.monotonic()' was captured AFTER the first await_done call's own early-check deadline (forge_sleep_s / 4) had already elapsed, but the assertion ('elapsed >= forge_sleep_s - 0.1') was written as if elapsed measured the FULL forge_sleep_s duration from process spawn. The achievable ceiling for elapsed from that start point is forge_sleep_s * 3/4 (0.375s for forge_sleep_s=0.5), already below the asserted 0.4s floor before any CI scheduling variance enters into it -- it only ever passed locally by luck (python startup overhead happening to push the real observed value just over 0.4s).

Fixed: start is now captured before the early-check call (i.e., at the actual process-spawn point), so elapsed genuinely measures the full real process lifetime and the margin means what it says. Verified 5/5 stable on macOS and 5/5 stable on real Linux+bwrap (brig-probe-amd64:latest) after the fix.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Both forged-done tests measure elapsed time from the actual process-spawn point, not from after the early-check's own deadline has already consumed part of the window
- [x] #2 Both tests pass stably (5+ consecutive runs) on macOS and real Linux+bwrap
- [ ] #3 CI (GitHub Actions) passes on a re-push
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Check `uv run just done` exited 0

(205 earlier lines omitted)
```text
[2m23:33:31.968[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m23:33:31.968[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m23:33:31.968[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m23:33:31.969[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m23:33:31.973[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m23:33:32.250[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 289ms
[2m23:33:32.252[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m23:33:32.253[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 507ms[39m[0m

   ┌───────────────────────────────────────────────────────────────┐
   │                                                               │
   │                                                               │
   │   [2mWebcomponents generated to:[22m                                 │
   │    site/assets/mkdocs_likec4/likec4_views.js                  │
   │                                                               │
   │   [2mSetup and usage instructions:[22m                               │
   │    [34mhttps://likec4.dev/tooling/code-generation/webcomponent/[39m   │
   │                                                               │
   │                                                               │
   └───────────────────────────────────────────────────────────────┘

uv run mkdocs build --strict

[31m │  ⚠  Warning from the Material for MkDocs team[0m
[31m │[0m
[31m │[0m  MkDocs 2.0, the underlying framework of Material for MkDocs,
[31m │[0m  will introduce backward-incompatible changes, including:
[31m │[0m
[31m │  × [0mAll plugins will stop working – the plugin system has been removed
[31m │  × [0mAll theme overrides will break – the theming system has been rewritten
[31m │  × [0mNo migration path exists – existing projects cannot be upgraded
[31m │  × [0mClosed contribution model – community members can't report bugs
[31m │  × [0mCurrently unlicensed – unsuitable for production use
[31m │[0m
[31m │[0m  Our full analysis:
[31m │[0m
[31m │[0m  [4mhttps://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/[0m
[0m
INFO    -  mkdocs-likec4: No projects discovered, using default root project
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /Users/brukhabtu/Downloads/brig-seed/site
INFO    -  mkdocs-likec4: Generating web component for default project from /Users/brukhabtu/Downloads/brig-seed/docs
INFO    -  Documentation built in 1.86 seconds

== architecture validate: PASS ==
[2m23:33:33.305[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m23:33:33.309[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m23:33:33.317[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m23:33:33.318[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m23:33:33.433[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m23:33:33.511[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m23:33:33.511[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 206ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

## Review (philosophy:reviewer, 2026-10-18)

Verdict: NOT CLOSED. The fix is correct and I would close it on its merits, but three
board-level facts stand in the way, and none of them are mine to change.

### The fix itself: verified, correct, test-only

- Diff (uncommitted, `tests/e2e/test_supervisor_link_gateway.py`) moves `start = time.monotonic()`
  above `supervisors.start(command, ())` in both affected tests and adds an explanatory comment.
  Nothing else changes: same assertions, same structure, same `await_done` deadlines (both still
  compute a fresh `time.monotonic()`, so the early check's own window is unaltered). No production
  code is touched.
- The CI log (run 39176499195) confirms the reading: the traceback points at line 166, the
  `elapsed` assertion, which sits *after* `assert outcome == real_exit_code`. The security property
  -- a forged done event is never trusted -- held in both failures. Only the auxiliary timing
  sanity check failed.
- Math: with `start` at the spawn point, `elapsed` now covers spawn + interpreter startup +
  `sleep(0.5)`, comfortably over the 0.4s floor, with no structural ceiling below it. Under the old
  placement the ceiling was `forge_sleep_s * 3/4` (0.375s) plus interpreter startup -- 0.395s on CI,
  0.4-something locally, which is exactly why it passed by luck. The check is genuinely auxiliary
  now: a trusted forged event would be caught first by `assert early is None`.
- Stability: 5/5 green on macOS, 5/5 green in a fresh privileged ubuntu:24.04/amd64 container with
  real bwrap (brig-probe-amd64:latest). `--collect-only` confirms the filter selected exactly the
  two changed functions.
- Full-tier check: pass (recorded above). `just gates` and `just typecheck` (mypy strict, 62 files):
  pass. The check reformatted and fixed nothing -- `git status` after it still shows only the one
  test file.

AC#1 and AC#2 are met on this evidence. AC#3 is not met and cannot be met from here.

### Findings

1. (blocking, process) AC#1 and AC#2 were already ticked in HEAD before review. Ticks are the
   reviewer's only change to the finish line; the worker ticking its own criteria inverts that. The
   state happens to be correct -- I verified both independently -- so nothing needs untreading, but
   the ticks carried no evidence at the time they were made.
2. (blocking, board) `board-check close` reports the criteria changed since acceptance in a1af15f
   (all three were added after), so the task needs the `finish-moved` label and a note saying what
   changed and why, committed by whoever moved them. A reviewer may not add that label.
3. (blocking) AC#3, "CI (GitHub Actions) passes on a re-push", is unmet and unverifiable within a
   review: it requires an actual push to the remote, which is the session owner's action. Pending,
   correctly left unticked.
4. No repro: this was caught by a one-shot CI run against uncommitted-at-the-time code, not by a
   committed failing test, so there is no earlier commit for `record-check --repro` to point at. The
   CI log for run 39176499195 (assert 0.39505254200000195 >= 0.4) is the repro of record, and the
   two tests themselves are the regression guard going forward.
5. The fix is still uncommitted. A reviewer does not commit the work it reviews.

None of the findings warrant a draft task: #1 and #2 are process corrections on this task, #3 is
pending by design, #4 is the documented escape hatch, #5 is the owner's next step.

### To close

Owner: add the `finish-moved` label with its note, commit the test file, confirm CI green on the
re-push, tick AC#3, then run close-task. Status left In Progress.
<!-- SECTION:NOTES:END -->
