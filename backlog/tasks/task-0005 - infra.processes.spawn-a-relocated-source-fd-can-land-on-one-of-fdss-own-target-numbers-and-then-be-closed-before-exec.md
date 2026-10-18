---
id: TASK-0005
title: >-
  infra.processes.spawn: a relocated source fd can land on one of fds's own
  target numbers and then be closed before exec
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 08:22'
updated_date: '2026-10-18 08:35'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - src/brig/infra/processes.py
  - tests/unit/test_processes.py
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Fix `_resolve_fd_sources` in src/brig/infra/processes.py: a relocated source fd must
   never land on any of `fds`'s own target numbers. Relocate with repeated `os.dup` (or
   `fcntl.F_DUPFD`/`os.dup2`-based allocation) until the result is outside the full
   target set, not just "not a target it already walked past" -- the bug was assuming
   os.dup can't return a target number, which is false whenever this process has a
   hole there.
2. Fix `_fd_actions` so no CLOSE action names a number a DUP2 action wrote a target
   onto -- order/dedupe the generated actions so a relocated-then-closed source and a
   final target never collide.
3. Add a test that forces the exact fd-allocation state DRAFT-0014/TASK-0004's review
   measured (a free hole at a target number below every other free fd) and fails
   against the old code -- not just a happy-path collision test.
4. Fix the docstring's false claim that os.dup cannot return one of fds's own targets.

### Proof
- The new test fails on the pre-fix code (confirm by stashing the fix locally) and
  passes after.
- just gates, just done green.
- Re-run TASK-0004's own end-to-end oracle (a supervised /bin/echo hello through
  create_bwrap_jail/run_jail, real Linux + bwrap in the brig-probe-amd64 container)
  still returns 0 after this fix, since this function sits underneath that path.

### Risks
- fd numbers are process-global, mutable state; a fix that works on macOS's fd layout
  but not Linux's (or vice versa) would hide the same bug again -- verify on both.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed both halves of the bug.

**`_resolve_fd_sources`**: relocation now uses `fcntl.fcntl(source, fcntl.F_DUPFD, max(targets) + 1)`
instead of a bare `os.dup(source)`. `F_DUPFD` takes a floor -- the lowest free fd *at or
above* a chosen number -- so the relocated fd is guaranteed to land past every target
regardless of which lower numbers happen to be free, instead of landing on whichever is
this process's lowest free fd overall (which is exactly a target number whenever this
process has a hole there). Docstring's false "fds's own targets are not candidates"
claim removed and replaced with why a bare `os.dup` could not be trusted here.

**`_fd_actions`**: the `CLOSE` list is now `set(resolved_fds.values()) - set(resolved_fds)`
(set difference against the target keys) instead of a blanket `resolved_fds.values()` --
no `CLOSE` action can ever name a number some `DUP2` in the same list wrote a target onto,
even if a future change to `_resolve_fd_sources` reintroduced the collision (the invariant
is enforced once, here, not relied on silently at the one caller).

**Regression test**: `tests/e2e/test_spawn_fd_redirection_collision.py` (e2e, not unit --
decision-0001 rule 4 restricts `tests/unit/` to `brig.domain` only, and the
`under-exposed-access` pypeeker rule blocks a test from reaching `_resolve_fd_sources`/
`_fd_actions` directly; an earlier `tests/unit/test_processes.py` draft was deleted for
exactly this). Forces the measured shape directly: one target's source is itself
(self-collision, the common case), and the other target's own number is a hole this test
frees and makes the process's lowest free fd right before the collision is resolved.
`_fill_fd_holes_below` first closes off every lower candidate this pytest process's own fd
table happens to carry, so which fd a bare `os.dup` would pick is forced, not ambient.

Confirmed discriminating by reconstructing the pre-fix `_resolve_fd_sources`/`_fd_actions`
(reverting just those two hunks in a scratch copy, not `git stash` -- the branch carries
other agents' uncommitted work) and running the new test against it: fails with
`OSError: [Errno 9] Bad file descriptor` from the probe child, exactly TASK-0005's own
measured signature. Restored the fix and reran: passes.

**`just gates`, `just done`**: both green (lint, typecheck, gates/pypeeker strict, pypeeker
rule tests, unit, integration x2, e2e, docs build, architecture validate, architecture lint
-- "done: all steps passed").

**Both platforms**: ran the same e2e suite in `brig-probe-amd64:latest`
(`--platform linux/amd64 --privileged`, repo copied to a writable `/work`, `uv sync`):
`tests/e2e` -> 31 passed, 2 skipped (real bwrap present there, so the bwrap-gated batteries
ran for real, not skipped as on macOS). `_fill_fd_holes_below`'s approach is
allocation-order-agnostic by construction (it forces the state rather than assuming
`/proc/self/fd` vs. the macOS probe-scan path land fds anywhere particular), so the same
test exercises the same collision on both.

**TASK-0004 oracle re-verified** in the same Linux container, post-fix: `create_bwrap_jail(("/bin/echo", "hello"))` through `run_jail` printed `hello` and returned exit code `0`; `destroy_jail` torn down clean.
<!-- SECTION:NOTES:END -->
