---
id: TASK-0036
title: Restate the ten laws against this design, each naming what holds it
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T04:07:00Z'
updated_date: '2026-11-04T20:23:00Z'
labels:
  - size-2
dependencies: []
type: task
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder that turns a refusal into a prompt can't offer the one grant that would allow a name pointing at a private address: decision-0009's rule is that only an IP-literal grant of that address opens it, and `EgressDecision` carries the name and port but not the address (`PrivateAddress.address` is dropped in `_judge`). An embedder asking its person needs the address to offer that IP-literal grant, with a warning that it is private.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each of the ten laws names only things that exist in brig (or says plainly it binds future work), and keeps its old SPEC intent
- [x] #2 Each law says which test holds it now, or that none does yet, so TASK-0001 #17's remaining work is visible
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker's report (Claude): 168a633. docs/spec/index.md's ten laws restated. What each names now: 1 the report's ceilings (decision-0008); 2 brig's refusals; 3 FsPolicy intent compiled per jail type (decision-0007); 4 channels (no observation surface today); 5 channels and the egress relay to come; 6 the supervisor's events, unreachable from the command (decision-0006); 7 interrupt_jail and destroy_jail; 8 grades from batteries, not events; 9 channel_exclusivity incl. socket places, and argv as a shared medium; 10 batteries and failing-test-first. Remaining for TASK-0001 #17: tests for laws 4 and 5 once something exists to hold them, law 3 across a second jail type, and a battery planting survivors for law 7. uv run just docs passes.

Check `uv run just done` exited 1

(262 earlier lines omitted)
```text
[2m04:13:56.616[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:13:56.621[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:13:58.887[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.42s
[2m04:13:58.891[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:13:58.893[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.3s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig/docs
INFO    -  Documentation built in 6.18 seconds

== architecture validate: PASS ==
[2m04:14:00.640[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:14:00.656[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m04:14:00.697[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:14:00.698[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:14:01.218[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m04:14:01.469[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m04:14:01.469[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 830ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: 1 step(s) failed: gates
error: recipe `done` failed on line 71 with exit code 1
```

Review (reviewer, 2026-11-03): NOT CLOSED. AC #2 met and ticked: every law names a test or says none does, and every cited test file exists (test_report_battery, test_grades, test_policy_refusal, test_fs_policy_battery, test_cwd_stdio_battery with its stdio and interpreter refusals, test_fs_policy_compile, test_supervisor_isolation_battery, test_interrupt_battery including the early-interrupt case, test_supervisor_reaps_orphans, the channel batteries, and the socket case in test_report_battery). Every name a law uses exists at HEAD (FsPolicy, reserve_channels, interrupt_jail, destroy_jail, channel_exclusivity, the started/done events). AC #1 not met: law 9 drops the old law's rule that argv is counted in the channel_exclusivity enumeration and is never excused from it, and makes it an untested promise. Filed as a draft (Law 9 excuses argv from channel_exclusivity). Full gate: just done fails at gates, from the TASK-0033 finding in test_report_battery, not from this task.

Worker, 2026-11-03, on the latest review, fixed at fe3f40d (see its message for each). TASK-0021: every mounted deny/mask caps fs_write/fs_read at BEST_EFFORT, with e2e cases for a host rename over a mask under a read-only root (this container keeps the mask, the reviewer's kernel did not: the grade allows for both) and a write at a deny. TASK-0034: PolicyStdioThroughLink names the link (infra.files.first_link). TASK-0035: an existing stdio path must be a regular file the embedder owns (PolicyStdioNotOwnFile; checked again once opened); e2e cases for another user's 0666 file and /dev/zero. TASK-0033: the gate failure came from the report battery writing os.environ; it now passes its environment as data; the rule's message names item writes. TASK-0036: law 9 counts argv as a shared medium again and says nothing tests it yet. uv run just done passes at fe3f40d.

Review 2026-11-03 (reviewer): closed. Full gate (uv run just done) exited 0 at fe3f40d plus board commits, recorded on TASK-0021; tree unchanged by it. AC#1 met: law 9 again counts argv as an enumerated shared medium, in the old law's words. AC#2 already met.
<!-- SECTION:NOTES:END -->
