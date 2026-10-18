---
id: TASK-0008
title: >-
  tests/e2e/test_spawn_fd_redirection_collision.py: _fill_fd_holes_below is a
  no-op, and its docstrings claim work it cannot do
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 08:40'
updated_date: '2026-10-18 13:20'
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
- [ ] #1 `_fill_fd_holes_below` is either removed, or given a caller that can actually find a hole to fill, so no dead code remains
- [ ] #2 The module docstring and the test's own comments state the real reason the fd allocation is deterministic (the `os.dup(0)` probe plus lowest-free allocation), and claim no behaviour the code does not have
- [ ] #3 `request_write_fd` is closed exactly once, with no bare `except OSError` masking a double close of a number that may have been reallocated
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
