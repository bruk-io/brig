---
id: TASK-0008
title: >-
  tests/e2e/test_spawn_fd_redirection_collision.py: _fill_fd_holes_below is a
  no-op, and its docstrings claim work it cannot do
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 08:40'
updated_date: '2026-10-18 14:54'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - tests/e2e/test_spawn_fd_redirection_collision.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0005.

`_fill_fd_holes_below(limit)` walks `range(3, limit)` and dup2s fd 0 onto every number `os.fstat` rejects. Its only caller passes `limit = next_fd`, where `next_fd = os.dup(0)` (then closed). `os.dup` returns this process's *lowest free* fd, so by construction every fd in `[3, next_fd)` is already open: `os.fstat` succeeds on all of them, `filled` is always `[]`, and the loop closes no hole and fills none.

The test is genuinely deterministic and genuinely discriminating -- reconstructing the pre-fix `_resolve_fd_sources`/`_fd_actions` makes it fail with `OSError: [Errno 9] Bad file descriptor` -- but the determinism comes from the `os.dup(0)` probe plus POSIX lowest-free allocation across the two `os.pipe()` calls, not from this helper.

Two docstrings assert otherwise, against decision-0001's 'what the code says must be true':
- the module docstring: '`_fill_fd_holes_below` first closes off every lower candidate this pytest process's own fd table happens to carry, so which fd `os.dup` would pick is this test's choice, not whatever this run's own fd table left behind'
- the helper's own docstring: 'Leaves this test free to force a hole at one specific, chosen number without some other, lower hole ... stealing the next `os.dup`/`os.pipe` allocation instead'

Also in the same cleanup: `request_write_fd` is closed at line 92 and closed again in the `finally` behind a bare `except OSError`. Post-fix nothing reallocates that number so it is harmless, but under the pre-fix code it is exactly the number `os.dup` grabs, so a discriminating run double-closes a reallocated fd.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `_fill_fd_holes_below` is either removed, or given a caller that can actually find a hole to fill, so no dead code remains
- [x] #2 The module docstring and the test's own comments state the real reason the fd allocation is deterministic (the `os.dup(0)` probe plus lowest-free allocation), and claim no behaviour the code does not have
- [x] #3 `request_write_fd` is closed exactly once, with no bare `except OSError` masking a double close of a number that may have been reallocated
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Remove `_fill_fd_holes_below` (dead code: its only caller's `limit = os.dup(0)`
   means every fd in range is already open by construction, so the loop always
   finds zero holes to fill) -- or give it a caller that can actually exercise it.
   Default to removal unless doing so would also remove the test's own
   determinism; if so, say explicitly in code why it stays.
2. Rewrite the module docstring and the helper's own former claims to state the
   real reason the fd allocation is deterministic: the `os.dup(0)` probe plus
   POSIX lowest-free-fd allocation across the two `os.pipe()` calls -- not a hole
   this helper closes off.
3. Fix `request_write_fd` being closed twice (once explicitly, once in a `finally`
   behind a bare `except OSError`) -- close it exactly once.

### Proof
- just gates, just done green.
- The test still fails against a reconstructed pre-fix `_resolve_fd_sources`/
  `_fd_actions` (re-confirm this directly, the same way TASK-0005's close review
  did, so removing the dead code didn't accidentally remove the discriminating
  property too) and passes against the real fix.

### Risks
- Low: test-only file, no production code touched. The one thing to verify
  carefully is that the test is still genuinely discriminating after the cleanup.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Removed `_fill_fd_holes_below` (dead: its only caller's `limit = os.dup(0)` means range(3,limit) is always fully open, zero holes found). Kept the `os.dup(0)`+close probe itself -- it is not dead, it establishes the real determinism (lowest-free-fd implies no holes below), so the two os.pipe() calls land on exactly 4 contiguous numbers. Rewrote the module and test docstrings to state that as the real reason instead of the removed helper's false claim. Fixed request_write_fd double-close by setting it to -1 right after its explicit close (same pattern already used for events_write_fd), so the finally block's loop skips it.

Reconfirmed discriminating: temporarily reconstructed pre-fix _resolve_fd_sources (bare os.dup instead of fcntl.F_DUPFD past max(targets)) and pre-fix _fd_actions (close_fds = set(resolved_fds.values()) with no target exclusion) in src/brig/infra/processes.py, ran `just test-selected tests/e2e/test_spawn_fd_redirection_collision.py` -- failed with OSError: [Errno 9] Bad file descriptor as expected. Restored the real file from a backup (git diff confirms clean, no production code changed).

just gates: pypeeker check --strict now fails on an unrelated pre-existing finding in src/brig/infra/state_dir.py (over-exposed-module-symbol on resolve/ensure) -- not touched by this task, landed by concurrent work (implement-supervisor-assembly). just done's lint step separately fails on unsorted imports in tests/unit/test_bwrap_compile.py -- also not touched by this task, mid-edit from concurrent TASK-0001.19/TASK-0009 work. Verified my own file in isolation: `ruff check`/`ruff format --check` on tests/e2e/test_spawn_fd_redirection_collision.py pass clean, `just typecheck` (mypy strict, whole repo) passes clean, and the targeted test passes alone and inside the full `just test-e2e` run (29 passed, 11 skipped, all real).

Check `uv run just done` exited 0

(194 earlier lines omitted)
```text
[2m14:46:25.760[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m14:46:25.760[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m14:46:25.760[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m14:46:25.761[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m14:46:25.765[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m14:46:26.038[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 285ms
[2m14:46:26.040[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m14:46:26.041[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 516ms[39m[0m

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
INFO    -  Documentation built in 1.80 seconds

== architecture validate: PASS ==
[2m14:46:26.740[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m14:46:26.743[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m14:46:26.752[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m14:46:26.752[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m14:46:26.866[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m14:46:26.946[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m14:46:26.946[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 207ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

Review (independent, close-work): all three acceptance criteria are genuinely met. AC#1 _fill_fd_holes_below removed, and its removal is correct -- os.dup(0) returns the lowest free fd, so range(3, limit) was fully open and the loop could never find a hole. AC#2 the module and test docstrings no longer claim the helper's work. AC#3 request_write_fd is set to -1 right after its explicit close, so the finally loop skips it: closed exactly once, nothing masked. Evidence: full-tier check 'uv run just done' exited 0 (recorded above); the test passes alone (1 passed in 0.02s).

NOT CLOSED, for a process reason only: as a bug this task needs a recorded repro, and record-check --repro refuses while tests/e2e/test_spawn_fd_redirection_collision.py is uncommitted. The reviewer is not permitted to commit. Whoever commits this task's file should then run: record-check TASK-0008 --repro -- uv run pytest tests/e2e/test_spawn_fd_redirection_collision.py -q, and close.

Findings (neither blocks): (1) medium -- the retained 'probe_fd = os.dup(0); os.close(probe_fd)' pair establishes nothing the next line does not, since os.pipe() already returns the lowest free fds by POSIX; its value is discarded, yet the new docstring credits the determinism to it. AC#2 names the probe as the real reason, so this is a finding against the criterion, not the work. (2) low -- the finally block's bare 'except OSError: pass' can no longer fire now that both early closes set their variable to -1. Both filed as DRAFT-0014.

No repro: the dead-code/docstring-overclaim fix and its own regression-discriminating test landed together in one commit (e9d5440) -- no earlier commit where the test exists against the still-dead-code version to run record-check --repro against. Same pattern as TASK-0002/TASK-0005/TASK-0001.19.
<!-- SECTION:NOTES:END -->
