---
id: TASK-0030
title: >-
  A SIGINT that reaches the supervisor before it installs its forwarding handler
  is dropped, and interrupt_jail still answers True
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T03:21:00Z'
updated_date: '2026-11-03T03:31:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0020 (e87d194). infra/supervisor/program.py _main starts the command (_start_child), closes _REQUEST_FD and emits 'started' (a pipe write that can block) before installing the SIGTERM/SIGINT handlers. As PID 1 of its PID namespace the supervisor ignores a signal it has no handler for, so an interrupt_jail in that window is sent (pidfd_send_signal succeeds, returns True) and lost. An embedder that interrupts only after its program said it is ready is in practice past the window, but nothing guarantees it, and an embedder that interrupts right after create gets True for nothing. Not measured. Fix: install the handlers (or block SIGINT/SIGTERM and unblock after) before starting the child, recording a signal that arrives before child_pid is known and forwarding it once it is.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A SIGINT or SIGTERM sent to the supervisor at any moment after the jail exists reaches the command, or interrupt_jail does not answer True
- [x] #2 A test sends SIGINT before the supervisor reports started and shows it delivered
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at 3ade49ef46fd, test files: tests/e2e/test_interrupt_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_interrupt_battery.py -k as_soon_as` exited 1

(17 earlier lines omitted)
```text
>           assert delivered, "the jail's command was running, yet nothing was signalled"
E           AssertionError: the jail's command was running, yet nothing was signalled
E           assert False

tests/e2e/test_interrupt_battery.py:86: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_interrupt_battery.py::test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost
1 failed, 2 deselected in 3.18s
```

Accepted 2026-11-03. Worker's report (Claude): fixed at 993f8bb. Measured first (the committed test, 3ade49e): an interrupt sent right after create_bwrap_jail returned found nothing to signal (interrupt_jail False while the command was about to run), and the review's window (a SIGINT before the supervisor's handler) was the other half: a PID 1 drops at send time any signal it has no handler for, blocked or not. Fix: the supervisor installs its SIGTERM/SIGINT handlers before it reads the exec request and forwards a signal held before the command existed once it does; signal_jail_pid1 waits up to 5 s while the jail is coming up (no PID 1 yet, or one with no child yet) and answers False once the jail is gone, its PID 1 a zombie, or its command finished. The test (20 interrupts straight after create) passes 3 runs in 3, with the two earlier interrupt tests. uv run just done passes at 993f8bb.

Check `uv run just done` exited 0

(257 earlier lines omitted)
```text
[2m03:28:27.386[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m03:28:27.441[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m03:28:27.509[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m03:28:30.217[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 3.01s
[2m03:28:30.219[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m03:28:30.221[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 4.3s[39m[0m

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
INFO    -  Documentation built in 7.28 seconds

== architecture validate: PASS ==
[2m03:28:33.260[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m03:28:33.292[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m03:28:33.379[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m03:28:33.380[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m03:28:34.259[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m03:28:34.955[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m03:28:34.956[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.6s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
