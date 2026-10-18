---
id: TASK-0011
title: >-
  tests/e2e/test_spawn_fd_redirection_collision.py: the os.dup(0) probe and the
  finally-block bare except are both dead
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 14:48'
updated_date: '2026-10-18 17:15'
labels:
  - brig
  - size-1
dependencies: []
modified_files:
  - tests/e2e/test_spawn_fd_redirection_collision.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found closing TASK-0008. TASK-0008 removed _fill_fd_holes_below but kept, and promoted in the docstring, the 'probe_fd = os.dup(0); os.close(probe_fd)' pair with the comment 'this process's lowest free fd -- proves no holes below it'. The probe discards its value and mutates nothing. POSIX already guarantees os.pipe() returns the lowest free fds, so the very next line 'request_read_fd, request_write_fd = os.pipe()' establishes the contiguity on its own; the probe proves nothing the code then uses. The module docstring's 'The allocation is deterministic without this test filling anything in: os.dup(0), immediately closed, always returns...' therefore credits determinism to a statement that does no work -- the same class of untrue claim TASK-0008 was filed to remove. TASK-0008's AC#2 named the probe as 'the real reason', so this is a finding against that criterion, not against the work. Separately, the finally block's 'try: os.close(fd) except OSError: pass' can no longer fire: every fd reaching it is either -1 (skipped) or open, since both early closes now set their variable to -1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The os.dup(0)/os.close probe is removed, or its comment and the module docstring say what it actually establishes
- [x] #2 The module docstring credits the determinism to POSIX lowest-free-fd allocation by os.pipe() itself
- [x] #3 The finally block closes each fd without a bare except OSError, or the except is justified by a path that can actually raise
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Remove the dead `probe_fd = os.dup(0); os.close(probe_fd)` pair (or, if keeping
   it for some reason not yet identified, rewrite its comment and the module
   docstring to say what it actually establishes -- default to removal, since
   nothing downstream uses it and os.pipe()'s own POSIX lowest-free-fd guarantee
   already does the real work).
2. Rewrite the module docstring to credit determinism to POSIX lowest-free-fd
   allocation by os.pipe() itself, not the removed probe.
3. Fix the finally block: every fd reaching it is either -1 (skipped) or open
   (both early closes already set their variable to -1), so the bare
   `except OSError: pass` can no longer fire -- remove it, or justify it against
   a real path that can still raise.

### Proof
- just gates, just done green.
- The test is still genuinely discriminating after the cleanup -- reconfirm by
  reconstructing the pre-TASK-0005-fix code and checking it still fails for the
  same reason, the same way TASK-0005's own close review did.

### Risks
- Low: test-only file. The only thing to verify carefully is that removing the
  dead probe and the finally's except doesn't silently change what the test
  actually proves.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Removed the dead `os.dup(0)`/`os.close` probe pair (zero net effect on the fd table, nothing downstream used its value). Rewrote the module docstring to credit determinism to POSIX's own lowest-free-fd guarantee for `os.pipe()`, not the removed probe. Removed the finally block's bare `except OSError: pass`: every fd reaching it is either -1 (skipped) or genuinely open (both early closes already set their variable to -1), so no path can raise there.

Reconfirmed discriminating power: monkeypatched `_resolve_fd_sources`/`_fd_actions` to the pre-TASK-0005-fix shape (bare `os.dup` instead of `fcntl.F_DUPFD`, blanket CLOSE instead of the target-excluding set) and ran the test function directly -- it failed for the right reason (probe's os.write got Bad file descriptor, exit code 1). Restored the real functions and reran -- passed.

`just gates` and `just done` both green.

Check `uv run just done` exited 0

(200 earlier lines omitted)
```text
[2m17:09:00.889[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m17:09:00.889[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m17:09:00.889[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m17:09:00.890[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m17:09:00.894[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m17:09:01.149[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 267ms
[2m17:09:01.151[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m17:09:01.152[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 480ms[39m[0m

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
INFO    -  Documentation built in 1.87 seconds

== architecture validate: PASS ==
[2m17:09:02.116[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m17:09:02.119[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m17:09:02.127[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m17:09:02.128[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m17:09:02.244[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m17:09:02.329[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m17:09:02.329[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 213ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

## Review (reviewer agent, not the implementer)

Verdict: NOT closed. AC#1 and AC#3 are met; AC#2 is not. Left In Progress, uncommitted.

AC#2 unmet -- the replacement docstring makes a new untrue claim, the same class
TASK-0008/TASK-0011 were filed to remove. Lines 19-22 now read: "`os.pipe()` always
returns this process's two lowest free fds, in order, so the two calls below land on
four consecutive numbers regardless of where they start." The premise is true; the
conclusion does not follow. Pipe #2 takes the two lowest free fds *above* pipe #1's
pair, which need not be adjacent to them whenever anything holds an fd open in
between. Measured counterexample in this very repo's interpreter: holding one fd open
between the two calls gives pipe1=(3,4), pipe2=(6,7) -- not consecutive -- and the test
still passes in that state. So the sentence is both false and not the reason the test
works.

The test needs only the shorter derivation: pipe #1 returns the two lowest free fds, so
every fd up to and including `request_write_fd` is open after it; closing
`request_write_fd` therefore makes that number this process's lowest free fd; pre-fix
`os.dup` returns the lowest free fd, lands on `target_events`, and the blanket CLOSE
undoes its DUP2. Pipe #2's numbers never enter the argument. Fix: drop the "four
consecutive numbers regardless of where they start" clause and end the derivation at
`request_write_fd` being the lowest free fd once closed. No draft filed -- this is a
one-sentence correction inside this task's own scope, not a separate defect.

AC#1 met: the `probe_fd = os.dup(0)` / `os.close(probe_fd)` pair is gone and nothing
downstream referenced its value.

AC#3 met, verified rather than taken on report: every fd reaching the `finally` is
either -1 (skipped) or genuinely open, so the unguarded `os.close(fd)` has no EBADF
path. `request_write_fd` and `events_write_fd` are each set to -1 immediately after
their early close; `request_read_fd` and `events_read_fd` are never closed before the
`finally`, because `spawn` closes only `_resolve_fd_sources`'s own relocated
duplicates (processes.py:391) and the posix_spawn file actions act on the child's fd
table, not this process's.

Independently redone, all green and not re-run needed next time:
- Discrimination: reconstructed the pre-TASK-0005-fix shape (bare `os.dup` in
  `_resolve_fd_sources`, blanket `set(resolved_fds.values())` CLOSE in `_fd_actions`)
  and ran the test function against it -- failed for the right reason (probe OSError
  [Errno 9] Bad file descriptor, exit code 1, AssertionError "probe did not exit
  cleanly"). Against the real functions it passes.
- `just gates` exit 0, `just done` exit 0, `record-check --tier full` all steps passed.

`No repro:` hatch: applies on the same grounds as TASK-0008 (dead-code/docstring
overclaim, fix and discriminating test in one commit, no earlier failing-state commit)
-- but moot until AC#2 is fixed.

No repro: this bug is a set of untrue claims in a test file's own prose plus two dead statements, not a behaviour a test can fail on. The fix and the file's own discriminating test landed together in one change, so there is no earlier failing-state commit for record-check --repro to point at. The test's discriminating power was reconfirmed by reconstructing the pre-TASK-0005-fix shape (recorded above).
<!-- SECTION:NOTES:END -->
