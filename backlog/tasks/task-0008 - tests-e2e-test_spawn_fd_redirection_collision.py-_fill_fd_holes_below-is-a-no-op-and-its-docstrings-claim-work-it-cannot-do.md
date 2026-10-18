---
id: TASK-0008
title: >-
  tests/e2e/test_spawn_fd_redirection_collision.py: _fill_fd_holes_below is a
  no-op, and its docstrings claim work it cannot do
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 08:40'
updated_date: '2026-10-18 13:26'
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
<!-- SECTION:NOTES:END -->
