---
id: TASK-0020
title: An embedder can interrupt a running jail's supervised command
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T11:00:00Z'
updated_date: '2026-11-03T03:20:00Z'
labels:
  - size-2
dependencies: []
type: task
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder that runs a long-lived program in a jail (an interpreter it sends work to over a channel, say) needs to interrupt the work in flight without ending the program: SIGINT to the supervised command, which the program turns into its own cancellation and keeps running.

At a7e7f45 nothing public signals the supervised command. The supervisor (`infra/supervisor/program.py`) installs a forwarding handler for SIGTERM only, and the embedder holds the supervisor's `Process`, not the command's. Measured: `os.killpg` of the supervisor's group with SIGINT never reached a command that had a SIGINT handler installed and was waiting for it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The public API delivers SIGINT to a running jail's supervised command (the supervisor forwards it) and returns whether it was delivered, as data
- [ ] #2 A test shows the command receives SIGINT and keeps running, and that interrupting a jail whose command has finished is answered, not raised past the driver exception boundary
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal. Worker's report (Claude): built at e87d194. interrupt_jail(jail) -> bool (presentation/api.py) sends SIGINT to the jail's PID 1 through infra.sockets.signal_jail_pid1: the candidate is found under the jail's bwrap as jail_pid1_namespace finds it, a pidfd is opened, then the candidate is checked again (PPid still the bwrap, innermost pid still 1) and the signal goes through the pidfd, so a recycled pid is never signalled; a PID 1 that is a zombie or has no child left answers False (the command finished). The supervisor forwards SIGINT to its child with SIGTERM's handler. tests/e2e/test_interrupt_battery.py: a command with a SIGINT handler is interrupted, keeps running, exits 0 (8 runs in 8); interrupting a finished jail answers False. Seen failing with the old supervisor (SIGTERM only): the running case fails, then passes with the fix. Found while building: a finished jail's supervisor can still exist for a moment after run_jail returns, and signalling it then succeeds; the zombie/no-child check is what makes the answer honest. uv run just done passes at e87d194.

Check `uv run just done` exited 0

(254 earlier lines omitted)
```text
[2m03:20:43.072[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m03:20:43.073[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m03:20:43.083[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m03:20:45.028[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.04s
[2m03:20:45.030[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m03:20:45.033[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 2.7s[39m[0m

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
INFO    -  Documentation built in 5.18 seconds

== architecture validate: PASS ==
[2m03:20:46.803[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m03:20:46.825[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m03:20:46.876[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m03:20:46.878[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m03:20:47.416[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m03:20:47.705[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m03:20:47.706[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 903ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
