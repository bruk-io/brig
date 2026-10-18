---
id: TASK-0014
title: >-
  infra.processes.spawn's SpawnError docstring is false on Linux: a missing
  argv[0] spawns successfully and dies 127
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 17:30'
updated_date: '2026-10-18 20:55'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - src/brig/infra/processes.py
  - tests/e2e/test_processes_gateway.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
src/brig/infra/processes.py's spawn() docstring says 'Raises: SpawnError: argv[0] could not be found on PATH or exec'd'. Measured false on Linux (glibc): os.posix_spawnp with an unresolvable bare command name does NOT raise -- it returns a pid and the child exits 127 (/bin/sh reporting 'command not found'). Reproduced independently in brig-probe-amd64:latest (ubuntu:24.04 amd64, system CPython 3.12.3/glibc 2.39): os.posix_spawnp('definitely-not-real-xyz', [...]) -> NORAISE pid=9, waitpid status 32512 == 127<<8. On macOS the same call does raise FileNotFoundError -> SpawnError, which is why the claim went unnoticed. Consequence is sharper than a wrong docstring: on Linux a missing argv[0] yields a healthy-looking SpawnedProcess that the caller tracks, reaps, and sees exit 127 -- SpawnError never fires, and no layer above distinguishes 'the binary was missing' from 'the command ran and returned 127'. Found while reviewing TASK-0012, whose shape-1 e2e test had to fall back to a macOS-only skipif for exactly this reason (an engineered PATH-starving repro does not reproduce on Linux).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 spawn()'s docstring states Linux's actual posix_spawnp behaviour for an unresolvable argv[0] (no raise; child exits 127) rather than claiming SpawnError covers it
- [x] #2 A decision is recorded on whether brig detects the shell-fallback/exit-127 shape explicitly, or accepts it, with the reasoning stated
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Decision (AC#2)

The exit-127 ambiguity cannot be closed after the fact: a legitimately-running
command choosing to exit 127 for its own reasons is indistinguishable, by exit code
alone, from glibc's own posix_spawn fallback reporting "command not found" that same
way. No detection mechanism can fully resolve this once the child has already been
spawned.

What CAN be closed: the common case (argv[0] genuinely unresolvable) can be caught
*before* ever calling posix_spawnp, by mirroring its own PATH-search semantics
(`shutil.which`, which already matches execvp's: a name containing "/" is checked
literally, never PATH-searched) and raising a real SpawnError proactively when it
fails. This is a best-effort narrowing, not a closure: a TOCTOU race (the binary
disappears between the check and the real spawn) still falls through to the
unexplained exit-127 path, same as today -- documented as the accepted residual, not
silently implied away.

### Order of work
1. Add the pre-check to `spawn()`: resolve `argv[0]` via `shutil.which(argv[0], path=...)`
   before calling `os.posix_spawnp` -- the search path must come from `env`'s own
   `PATH` when `env` is given (since that's what the new process's own exec search
   actually uses), falling back to this process's `os.environ.get("PATH", os.defpath)`
   only when `env` is None. Raise `SpawnError` (a real errno -- ENOENT is the natural
   choice, matching what macOS's own OS-level raise already reports) when it fails to
   resolve, before any fork/spawn happens.
2. Fix `spawn()`'s and `SpawnError`'s own docstrings to state the real, narrowed
   guarantee: `SpawnError` fires for a name this pre-check cannot resolve, on every
   platform; it does NOT fire, and cannot structurally be made to fire, for a name
   that resolves but whose exec then fails for some later reason the OS reports as a
   plain exit code (the Linux glibc fallback shape this task was filed for) -- name
   the residual TOCTOU race explicitly rather than implying the gap is closed.
3. Tests: an unresolvable bare name now raises SpawnError via the pre-check on BOTH
   platforms (previously only macOS raised, via the OS itself); a resolvable bare
   name is unaffected; a direct path (containing "/") bypasses PATH search entirely,
   matching execvp's own semantics, and is unaffected whether it exists or not (that
   case was already real OS-level behavior before this task, not changed here);
   `env`'s own PATH, when given, is what the pre-check actually searches, not this
   process's own `os.environ`.

### Proof
- just gates, just typecheck, just done green.
- Real Linux + bwrap (brig-probe-amd64:latest): confirm the pre-check actually fires
  there for the exact shape this task was filed from (an unresolvable bare command),
  converting today's mysterious exit 127 into a real SpawnError.
- macOS: confirm nothing regresses for the cases that already worked (the OS's own
  raise) and that the new pre-check doesn't double-raise or behave differently there.

### Risks
- Getting the PATH source wrong (using this process's own `os.environ` when `env`
  overrides it) would make the pre-check check the wrong search path entirely --
  verify with a case where `env`'s PATH differs from this process's own.
- Don't let the pre-check's own cost (a real filesystem walk) become a path visible
  to a caller as a new, unexpected latency source on every spawn -- `shutil.which`'s
  own cost is bounded by PATH's length, same order of magnitude as the exec itself.
<!-- SECTION:PLAN:END -->
