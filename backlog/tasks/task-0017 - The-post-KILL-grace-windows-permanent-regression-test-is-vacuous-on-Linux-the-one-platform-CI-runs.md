---
id: TASK-0017
title: >-
  The post-KILL grace window's permanent regression test is vacuous on Linux,
  the one platform CI runs
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 20:05'
updated_date: '2026-10-18 22:26'
labels:
  - brig
  - size-1
dependencies: []
modified_files:
  - tests/e2e/test_processes_gateway.py
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. tests/e2e/test_processes_gateway.py::test_destroy_jail_survives_the_leader_exiting_before_its_group
   has a 0.05s pre-sleep between spawn and destroy_jail that hides the race on
   Linux (measured: 0/150 failures at kill_grace_s=0.0 there, identical to the
   default -- proves nothing). Without any pre-sleep, the race is real and
   decisive on Linux (200/200 failures at kill_grace_s=0.0). Drop the pre-sleep
   (or add a second, no-pre-sleep variant alongside the existing one) so the test
   actually exercises the race on the platform CI runs.
2. Re-measure on BOTH platforms after the change: confirm it still passes against
   the landed grace window and would fail with it disabled, on macOS AND Linux.

### Proof
- just done green on macOS.
- Real Linux + bwrap (brig-probe-amd64:latest): the test fails when kill_grace_s
  is forced to 0.0 (temporarily, to prove discrimination) and passes against the
  real default -- not the other way around.

### Risks
- Removing the pre-sleep entirely might make the test flakier in some OTHER way
  on macOS (timing-sensitive) -- re-measure there too, don't assume dropping the
  sleep is free on both platforms just because it's necessary on one.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Check `uv run just done` exited 0

(205 earlier lines omitted)
```text
[2m22:26:43.713[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m22:26:43.713[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m22:26:43.714[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m22:26:43.714[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m22:26:43.718[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m22:26:43.975[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 268ms
[2m22:26:43.977[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m22:26:43.978[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 485ms[39m[0m

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
INFO    -  Documentation built in 1.45 seconds

== architecture validate: PASS ==
[2m22:26:44.903[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m22:26:44.906[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m22:26:44.915[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m22:26:44.915[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m22:26:45.027[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m22:26:45.105[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m22:26:45.105[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 203ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```
<!-- SECTION:NOTES:END -->
