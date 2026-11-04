---
id: TASK-0054
title: >-
  An egress decision refused for a private address names the address the name
  resolved to
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T20:22:00Z'
updated_date: '2026-11-04T20:30:00Z'
labels:
  - size-1
  - egress
dependencies: []
modified_files:
  - src/brig/domain/policy/egress_record.py
  - src/brig/infra/proxy/program.py
  - src/brig/presentation/jail.py
  - tests/e2e/test_egress_live_battery.py
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder that turns a refusal into a prompt can't offer the one grant that would allow a name pointing at a private address: decision-0009's rule is that only an IP-literal grant of that address opens it, and `EgressDecision` carries the name and port but not the address (`PrivateAddress.address` is dropped in `_judge`). An embedder asking its person needs the address to offer that IP-literal grant, with a warning that it is private.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A private-address refusal's decision line and `EgressDecision.address` name the address the name resolved to; every other decision's is ''
- [x] #2 A real-jail test: a name granted by host, resolving to 127.0.0.1 with no IP-literal grant, is refused with reason private-address and address 127.0.0.1
- [x] #3 just done passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Thread the address through the one path a decision takes: `_judge` passes `str(outcome.address)` for a `PrivateAddress` ('' otherwise) to `_Decisions.record`, which writes it as an `address` field after `reason`; `presentation.jail._decision` reads it (a str, required) into a new `EgressDecision.address`.

### Order of work
1. `EgressDecision.address` and its docstring; `_DecisionFields` and `record`; `_judge`; `_decision`.
2. The live battery's field-order assertion gains `address` ('' for each of its decisions).
3. A real-jail test: `near.test` granted by name, `egress_hosts` mapping it to 127.0.0.1, no IP-literal grant; one CONNECT through the proxy is refused, and its decision reads reason private-address, address 127.0.0.1.

### Risks
- A decision line without the field is dropped like an unreadable one (no backwards compatibility: the proxy and the reader ship together).

### Proof
The new real-jail test fails before the change (no `address`); `just done` passes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Check `uv run python3 scripts/run_done.py` exited 0

(348 earlier lines omitted)
```text
[2m20:27:59.970[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m20:27:59.977[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m20:28:00.010[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m20:28:01.823[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 1.93s
[2m20:28:01.826[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m20:28:01.829[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 2.6s[39m[0m

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
INFO    -  Documentation built in 5.00 seconds

== architecture validate: PASS ==
[2m20:28:03.396[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m20:28:03.409[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m20:28:03.436[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m20:28:03.436[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m20:28:03.812[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m20:28:04.118[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m20:28:04.119[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 724ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Check `uv run just done` exited 0

(350 earlier lines omitted)
```text
[2m20:29:59.494[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m20:29:59.501[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m20:29:59.579[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m20:30:01.628[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.26s
[2m20:30:01.631[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m20:30:01.634[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3s[39m[0m

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
INFO    -  Documentation built in 5.29 seconds

== architecture validate: PASS ==
[2m20:30:03.064[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m20:30:03.079[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m20:30:03.102[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m20:30:03.103[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m20:30:03.491[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m20:30:03.798[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m20:30:03.799[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 736ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
