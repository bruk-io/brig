---
id: TASK-0029
title: >-
  Refuse a policy that does not reach the supervisor's interpreter, before bwrap
  runs
status: Done
assignee:
  - '@claude'
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T03:46:00Z'
labels:
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. The supervisor runs under the embedder's `sys.executable` (`_supervisor_path`). Measured: a policy that does not bind it (or a link on the way to it, such as a uv-managed Python's `cpython-3.15-<platform>` link) makes bwrap print `execvp ... No such file` on the embedder's stderr and `run_jail` raise `JailExitUnknown: jail process already reaped elsewhere`, which names neither the cause nor the fix. Same shape as `_check_state_dir_reachable`: a pure check over the policy and the interpreter's path and links, raised as a typed error.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 create refuses, before bwrap runs, a policy under which the supervisor's interpreter or a link on the way to it is not reachable, with a typed error naming the path
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03. Worker's report (Claude): built at 55336cd. infra.files.link_chain(path) lists every path a lookup passes through (the path, then the path with each link on the way replaced by its target, until none is; 40 links at most, as the kernel). domain interpreter_refusal requires each to be inside a root of the policy and under no mask (a mount shows a link's target only where the link is mounted too); create_bwrap_jail checks sys.executable's chain before writing anything and raises PolicyInterpreterUnreachable naming the first path missed. e2e: a system-tree-only policy is refused naming sys.executable (skips where the interpreter lives under the system tree); unit cases for a venv -> version-manager link -> install chain, mounted, half-mounted and masked. uv run just done passes.

Check `uv run just done` exited 0

(250 earlier lines omitted)
```text
[2m03:45:39.222[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m03:45:39.229[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m03:45:39.249[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m03:45:41.575[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.42s
[2m03:45:41.578[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m03:45:41.590[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.3s[39m[0m

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
INFO    -  Documentation built in 6.02 seconds

== architecture validate: PASS ==
[2m03:45:43.538[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m03:45:43.555[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m03:45:43.597[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m03:45:43.597[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m03:45:44.112[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m03:45:44.448[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m03:45:44.449[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 911ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Closed by review 2026-11-03. Full gate passes. AC#1 met: link_chain verified on relative, absolute, mid-path and chained links (a loop returns a bounded chain); a policy missing the cpython-3.15 link is refused naming it, and bwrap given that policy fails with execvp No such file (measured); a full system+venv+uv policy is accepted and the jail runs (exit 0). Findings filed as draft 'A policy without the interpreter's ELF loader and libraries passes interpreter_refusal...': loader/libc not checked (accepted policy still fails with the old symptom), over-refusal when the interpreter link itself is the root, lexical '..' in link_chain.
<!-- SECTION:NOTES:END -->
