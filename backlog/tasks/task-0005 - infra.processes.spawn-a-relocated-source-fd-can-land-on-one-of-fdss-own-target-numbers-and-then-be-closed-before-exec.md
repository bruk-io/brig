---
id: TASK-0005
title: >-
  infra.processes.spawn: a relocated source fd can land on one of fds's own
  target numbers and then be closed before exec
status: To Do
assignee: []
created_date: '2026-10-18 08:22'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0004 (AC#3). `_resolve_fd_sources` relocates a source fd that collides with a target via `os.dup`, but never checks the number `os.dup` returns against the target set. `os.dup` returns the lowest free fd, and a target number (wire.REQUEST_FD=3 / wire.EVENTS_FD=4) is free -- hence a candidate -- whenever this process has a hole there. The function's docstring states the opposite as its justification ('fds's own targets are not candidates: they are not fds this process has open at all'); that reasoning is false.

`_fd_actions` then emits one unconditional `POSIX_SPAWN_CLOSE` per resolved source value, so the relocated number is closed in the child *after* a later `DUP2` has already written the real channel onto it.

Measured through the real code on macOS (no mocking):

    a, b = os.pipe()   # 3, 4
    c, d = os.pipe()   # 5, 6
    os.close(b)        # fd 4 free and lowest
    _resolve_fd_sources({3: a, 4: d}) -> ({3: 4, 4: 6}, (4,))
    _fd_actions(...)   -> [DUP2 4->3, DUP2 6->4, CLOSE 4, CLOSE 6]

End to end: `processes.spawn((python, '-I', '-c', 'os.write(4, b\"x\")'), (1, 2), fds={3: a, 4: d})` in that layout -> the child reports 'fd4 FAILED: [Errno 9] Bad file descriptor'. In the supervisor's real use that is `program.py` losing its events channel silently, for an embedder whose fd table merely has a hole at 3 or 4.

No test covers the collision path at all: deleting the whole relocation branch leaves the suite green (privileged ubuntu:24.04 amd64, `pytest tests/` -> 58 passed, 2 skipped), because under uv/pytest the pipes land at fds 12-15 and no collision arises. The branch is nonetheless load-bearing: monkeypatching `_resolve_fd_sources` to the identity on macOS (pipes at 3-6) makes `LiveSupervisors.start(('/bin/echo','hello'))` fail with SupervisorSpawnError (program.py: EBADF at _read_exec_request).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A source fd relocated out of a collision never lands on any of `fds`'s own target numbers (e.g. dup repeatedly until outside the target set, or fcntl.F_DUPFD past max(targets)), and no CLOSE action names a number a DUP2 action wrote a target onto
- [ ] #2 A test forces the fd-allocation state that reproduces this (a free hole at a target number below every other free fd) and fails against today's code, so the collision path has regression coverage that discriminates
- [ ] #3 `_resolve_fd_sources`'s docstring no longer claims target numbers cannot be returned by os.dup
<!-- AC:END -->
