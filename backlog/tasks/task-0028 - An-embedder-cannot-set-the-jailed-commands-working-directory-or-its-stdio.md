---
id: TASK-0028
title: An embedder cannot set the jailed command's working directory or its stdio
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T03:29:00Z'
labels:
  - size-3
  - finish-moved
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. Measured: the command starts in the embedder's own working directory (there is no `--chdir`), and its stdout and stderr come out on the embedder's own fds (`_INHERITABLE_FDS = (0, 1, 2)`, and `infra/supervisor/link.py` hands the supervisor the embedder's 0/1/2). An embedder that runs several jails in different directories cannot chdir its own process to suit each, and one that owns its terminal (a TUI) has a jailed traceback painted over it. `Plan.inheritable_fds` reaches no effect, so the fd policy sits hard-coded in infra.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 create takes a working directory for the command, and an stdio policy (at least: stdout and stderr to a file brig returns, or to nothing)
- [ ] #2 The fd allow-list the supervisor and its command start with comes from the embedder's Stdio, not a constant in infra or bwrap; Plan.inheritable_fds, which reached no effect, is gone
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal. Criterion #2 restated (finish-moved) before review: as written it asked Plan.inheritable_fds to be what infra applies, but that field reached no effect and the fd policy belongs with the stdio an embedder states, so the field and bwrap's (0, 1, 2) constant are removed and Stdio is the allow-list. Worker's report (Claude): built at d98bc84. create_bwrap_jail(cwd=..., stdio=Stdio(...)); cwd is bwrap's --chdir (domain cwd_refusal: absolute, inside a root, under no mask; PolicyCwdOutsideRoots). Stdio (domain/policy/stdio.py): each of fd 0, 1, 2 a host path or the embedder's own; infra/supervisor/link.py opens them (stdin read-only, stdout and stderr O_APPEND|O_CREAT 0600) and spawns the supervisor with them as fds 0-2 and only the unnamed ones inherited; an open failure is JailSpawnFailed through the driver. tests/e2e/test_cwd_stdio_battery.py: cwd, stdin, stdout, stderr to files (stdout 0600), stderr to /dev/null with stdout the embedder's own (capfd), a cwd outside every root refused; unit cases for --chdir's place and cwd_refusal. uv run just done passes at 993f8bb.

Check `uv run just done` exited 0

(256 earlier lines omitted)
```text
[2m03:29:40.945[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m03:29:40.950[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m03:29:41.026[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m03:29:43.467[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.70s
[2m03:29:43.470[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m03:29:43.473[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.7s[39m[0m

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
INFO    -  Documentation built in 6.45 seconds

== architecture validate: PASS ==
[2m03:29:45.333[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m03:29:45.350[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m03:29:45.394[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m03:29:45.395[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m03:29:45.828[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m03:29:46.060[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m03:29:46.061[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 729ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
