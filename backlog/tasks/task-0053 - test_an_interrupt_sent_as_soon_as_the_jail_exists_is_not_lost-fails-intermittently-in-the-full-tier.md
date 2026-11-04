---
id: TASK-0053
title: >-
  test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost fails
  intermittently in the full tier
status: In Progress
assignee: []
created_date: '2026-11-04T14:23:00Z'
updated_date: '2026-11-04T15:19:00Z'
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
- [x] #1 The failing assert and its cause are identified, from a run that keeps the test's output
- [x] #2 The test passes 10 full-tier runs in a row, or the window it shows is fixed with a test that pins it
- [x] #3 The failing assert of test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost is named, with its message, from runs under load (the full tier, or the e2e layer run with other e2e tests in parallel) until it fails at least 3 times
- [x] #4 The cause is found and stated: a flaw in the test (a timing assumption) or a lost interrupt in brig (TASK-0030's window open again); if brig's, a repro is recorded and the fix keeps the interrupt from being lost
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

Worker, 2026-11-04: cause found; a flaw in the test, not a lost interrupt in brig. Fixed in f9c4376 (test only).

**Asserts seen.** Six failures under load, every one the first assert: `AssertionError: interrupt_jail said True and nothing arrived` / `assert not (True and 0 == 0)`. The second assert never fired. Load: the test run on its own, repeatedly, while the whole e2e layer ran in a loop alongside, plus 4 to 6 CPU busy-loops on this 4-core host. A scratchpad pytest plugin (measurement only, not committed) kept each failure's message, the timing of each create/interrupt/run, and a read-only `/proc` snapshot of PID 1 and its child just before and after the signal (no ptrace, no /proc/<pid>/mem). The e2e layer alone did not reproduce it here: 14 serial runs with 4 busy-loops and 45 runs three at a time (with 6 busy-loops for the later ones) never failed this test.

**Cause.** The interrupt does reach the command. At the moment of a failing signal, PID 1 was the supervisor with its SIGINT handler installed (SigCgt 0x4002) and its child was the command, already past exec with Python's own SIGINT handler installed (SigCgt 0x2). The three failures whose stderr was kept each end with the command's own `Exception ignored while calling weakref callback <function _get_module_lock.<locals>.cb ...>: ... KeyboardInterrupt`: a SIGINT that lands while the interpreter is still starting up can raise KeyboardInterrupt inside one of importlib's weakref callbacks, where CPython reports it as unraisable and carries on. The command then sleeps the full 3 s and exits 0, which the test read as "nothing arrived". It needs no jail: 580 SIGINTs sent 2 to 16 ms after spawning a bare `python -I -c "import time; time.sleep(3)"` gave 293 exits by the signal (-2), 286 exits of 1 (KeyboardInterrupt in site import, fatal) and 1 exit of 0, with the same weakref message. Load makes the interpreter's startup longer, so more interrupts land inside it. TASK-0030's window is not open again, and TASK-0001.30/TASK-0045 are not involved.

**Fix.** The command is now `/bin/sleep 3`. It never handles SIGINT, so an interrupt that arrives at any point after the spawn kills it (glibc's posix_spawn resets the supervisor's handler to the default in the child before exec). The assert is stronger: the exit code must be exactly -SIGINT, not merely non-zero. The property is unchanged: an interrupt sent as soon as the jail exists reaches the command.

**Evidence that it holds.** 50 rounds under the same load (e2e layer loop, 6 busy-loops, the pre-signal /proc probe), each round running the fixed test and then HEAD's old test: the fixed test passed 50 of 50 (1000 interrupts: interrupt_jail True every time, exit -2 every time). The old test failed 2 of 50 in the same rounds (992 interrupts: 842 exits of -2, 148 of 1, 2 of 0), both with the weakref message. Without the probe, a second set of 50 rounds passed both 50 of 50: the probe's small delay moves the signal into the interpreter's startup. Full tier: record-check --tier full passed (recorded above).

**Seen in passing, not this task:** under the parallel and busy-loop load, the e2e layer also failed `test_egress_connection_caps.py::test_destroy_jail_at_the_cap_leaves_no_proxy_process_thread_or_fd` (twice), `test_egress_connection_caps.py::test_the_proxy_serves_at_most_its_cap_and_refuses_one_more_with_403_or_socks_0x01` (once) and `test_report_battery.py::test_fs_read_a_mask_the_host_renames_over_is_undone_so_the_report_says_best_effort` (once). Their messages were not kept. Criteria left unticked for the reviewer.

Worker, correction to "seen in passing" above (the counts and messages, from the kept run output): in 59 e2e-layer runs under load, other tests failed six times. `test_egress_connection_caps.py::test_the_proxy_serves_at_most_its_cap_and_refuses_one_more_with_403_or_socks_0x01` failed 3 times, each `assert 12 == (7 + (2 * 3))` on the fd count. `test_egress_connection_caps.py::test_destroy_jail_at_the_cap_leaves_no_proxy_process_thread_or_fd` failed twice, each with an extra `process_request_thread` thread left over. `test_report_battery.py::test_fs_read_a_mask_the_host_renames_over_is_undone_so_the_report_says_best_effort` failed once with `JailExitUnknown: jail's exit code was lost before it was reported`. All of these were three e2e layers at a time or with busy-loops, which is heavier than the full tier. Not investigated.

Check `uv run just done` exited 0

(350 earlier lines omitted)
```text
[2m15:19:08.653[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m15:19:08.655[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m15:19:08.724[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m15:19:11.274[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.69s
[2m15:19:11.277[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m15:19:11.281[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.9s[39m[0m

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
INFO    -  Documentation built in 6.83 seconds

== architecture validate: PASS ==
[2m15:19:13.151[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m15:19:13.178[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m15:19:13.202[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m15:19:13.203[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m15:19:13.897[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m15:19:14.732[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m15:19:14.753[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.6s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
