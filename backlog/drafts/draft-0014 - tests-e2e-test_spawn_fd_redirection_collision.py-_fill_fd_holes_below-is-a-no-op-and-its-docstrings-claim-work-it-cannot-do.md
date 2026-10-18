---
id: DRAFT-0014
title: >-
  tests/e2e/test_spawn_fd_redirection_collision.py: _fill_fd_holes_below is a
  no-op, and its docstrings claim work it cannot do
status: Draft
assignee: []
created_date: '2026-10-18 08:40'
labels: []
dependencies: []
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
