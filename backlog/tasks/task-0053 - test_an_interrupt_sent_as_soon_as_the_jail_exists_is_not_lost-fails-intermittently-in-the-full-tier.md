---
id: TASK-0053
title: >-
  test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost fails
  intermittently in the full tier
status: To Do
assignee: []
created_date: '2026-11-04T14:23:00Z'
updated_date: '2026-11-04T15:15:00Z'
labels:
  - brig
  - tests
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reviewing TASK-0050/0001.38/0051/0052 on claude/small-bugs (2026-11-04): five full-tier runs (record-check --tier full) of one tree failed twice, both times only tests/e2e/test_interrupt_battery.py::test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost (recorded on TASK-0050 and TASK-0052); three passed. Alone it passed 3 of 3 and 8 of 8 run in parallel. TASK-0047's worker saw an unnamed full-tier e2e failure of the same kind. The branch does not touch the signal path (signal_jail_pid1 and _pid1_under; the change is to _nspid and jail_pid1_namespace). record-check keeps only the tail of the output, so neither assertion message was kept: which of the test's two asserts fires is unknown. Realistic path: CI under load goes red on a change that has nothing to do with it, or a lost-interrupt window that TASK-0030 closed is open again under load.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The failing assert and its cause are identified, from a run that keeps the test's output
- [ ] #2 The test passes 10 full-tier runs in a row, or the window it shows is fixed with a test that pins it
- [ ] #3 The failing assert of test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost is named, with its message, from runs under load (the full tier, or the e2e layer run with other e2e tests in parallel) until it fails at least 3 times
- [ ] #4 The cause is found and stated: a flaw in the test (a timing assumption) or a lost interrupt in brig (TASK-0030's window open again); if brig's, a repro is recorded and the fix keeps the interrupt from being lost
- [ ] #5 The test passes 50 of 50 runs under the same load
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted; criteria written right after promotion (finish-moved for that reason only).

Check `uv run just done` exited 0

(358 earlier lines omitted)
```text
[2m15:15:26.169[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m15:15:26.212[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m15:15:26.214[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m15:15:29.080[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.95s
[2m15:15:29.083[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m15:15:29.085[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 4.3s[39m[0m

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
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

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
INFO    -  Building documentation to directory: /home/user/brig-pins/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-pins/docs
INFO    -  Documentation built in 7.10 seconds

== architecture validate: PASS ==
[2m15:15:30.583[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m15:15:30.601[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m15:15:30.682[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m15:15:30.682[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m15:15:31.310[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m15:15:31.752[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m15:15:31.752[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.1s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
