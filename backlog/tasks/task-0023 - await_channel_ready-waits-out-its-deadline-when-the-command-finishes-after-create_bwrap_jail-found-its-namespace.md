---
id: TASK-0023
title: >-
  await_channel_ready waits out its deadline when the command finishes after
  create_bwrap_jail found its namespace
status: Done
assignee:
  - '@claude'
created_date: '2026-11-03T02:42:00Z'
updated_date: '2026-11-03T02:51:00Z'
labels:
  - size-2
dependencies: []
type: bug
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0022, 2026-11-03. tests/e2e/test_channel_jail_finished.py's first test assumes `true` finishes before `create_bwrap_jail`'s namespace scan finds the jail's PID 1 (TASK-0001.30). When the scan wins instead, `channel_namespace_fd` is set, the command then exits, and `await_channel_ready` polls an empty channel until `timeout_s` and answers `ChannelNotReady`, never `ChannelJailFinished`. Measured at 739dd94 with no change: 1 run in 3 failed, after 10.22s (the test's deadline). TASK-0022's supervisor does more before starting its command (it makes itself non-dumpable), so the scan wins every time and the test fails 5 in 5. The property the test names (a jail whose command finished reads as finished, at once) does not depend on which side of the race the scan landed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 await_channel_ready answers ChannelJailFinished as soon as the jail's own process has exited, whether or not create_bwrap_jail held its namespace, and never reaps it (decision-0003: peek, not reap)
- [x] #2 test_channel_jail_finished.py asserts that property and its timing, not which side of the scan's race it landed on, and passes 10 runs in 10 with TASK-0022's supervisor
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at 08aaf4a2516a, test files: tests/e2e/test_channel_jail_finished.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_channel_jail_finished.py::test_a_jail_whose_command_exits_at_once_is_created_and_reads_as_finished` exited 1

(29 earlier lines omitted)
```text
            destroy_jail(jail, directories=directories)
    
>       assert outcome == ChannelJailFinished()
E       assert ChannelNotReady() == ChannelJailFinished()
E        +  where ChannelJailFinished() = ChannelJailFinished()

tests/e2e/test_channel_jail_finished.py:85: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_channel_jail_finished.py::test_a_jail_whose_command_exits_at_once_is_created_and_reads_as_finished
1 failed in 10.15s
```

Worker's report (Claude, 2026-11-03). await_channel_ready takes a processes port and, after every not-ready attempt, peeks the jail's own process (decision-0003: never reaped); once it has exited it answers ChannelJailFinished. tests/e2e/test_channel_jail_finished.py's first test asserts the outcome and that it comes within 2s instead of which side of the scan's race it landed on (committed alone first, 0f0ac9d; the repro above failed there, on the second of two runs, the race being a race). A new integration test (fakes) asserts a peek after one not-ready attempt, ChannelJailFinished at once, nothing reaped or released; the four existing readiness integration tests pass a FakeProcesses whose process is running. With TASK-0022's supervisor the e2e test passed 10 runs in 10. uv run just done passes at 08aaf4a (recorded on TASK-0022, same tree).

Check `uv run just done` exited 0

(246 earlier lines omitted)
```text
[2m02:51:01.142[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m02:51:01.195[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m02:51:01.275[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m02:51:04.043[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 3.06s
[2m02:51:04.051[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m02:51:04.054[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 4.4s[39m[0m

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
INFO    -  Documentation built in 7.60 seconds

== architecture validate: PASS ==
[2m02:51:06.134[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m02:51:06.159[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m02:51:06.266[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m02:51:06.267[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m02:51:07.035[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m02:51:07.422[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m02:51:07.423[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.2s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Reviewed (reviewer, 2026-11-03): closed. AC #1: await_channel_ready peeks after each not-ready attempt; infra peek is waitid(WEXITED|WNOWAIT|WNOHANG), so it never reaps (decision-0003). AC #2: the e2e test asserts outcome and a 2s bound; reviewer ran it 10/10 passing with TASK-0022's supervisor; the new integration test asserts through FakeProcesses (peek_attempts, reaped == [], released == []). Full gate (uv run just done) passed, recorded. Minor note, no task: a ProcessUnknown peek (pid already released) also answers ChannelJailFinished, since the check is 'is not None'; that reads as finished, which is reasonable, but the docstring says only 'has exited'.
<!-- SECTION:NOTES:END -->
