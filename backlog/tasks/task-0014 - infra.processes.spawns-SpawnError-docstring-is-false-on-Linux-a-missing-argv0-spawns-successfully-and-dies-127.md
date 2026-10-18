---
id: TASK-0014
title: >-
  infra.processes.spawn's SpawnError docstring is false on Linux: a missing
  argv[0] spawns successfully and dies 127
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 17:30'
updated_date: '2026-10-18 21:04'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Implementation report

Implemented exactly as planned in shape, with one load-bearing correction to the
plan's stated mechanism, caught by the plan's own Risks section (verify with a
case where env's PATH differs from this process's own) and confirmed by advisor.

**The plan's instruction was measured false.** The plan said the pre-check's
search path should come from env's own PATH when env is given, "since that's
what the new process's own exec search actually uses." Measured directly, on
both Apple libc (macOS) and glibc (brig-probe-amd64:latest, Linux): `os.posix_spawnp`'s
own PATH search consults the *calling* process's real `os.environ["PATH"]`,
never the `env` argument -- `env` only becomes the child's own environment once
exec succeeds. Proof: `os.posix_spawnp(name, argv, {"PATH": bin_dir})` with this
process's real PATH unchanged fails to find a binary that only exists in
`bin_dir` (on Linux: NORAISE, child exits 127 -- the exact shape this task was
filed for, now reproduced via `env` instead of a bare missing command); the
mirror case (narrow `env["PATH"]`, name resolvable on this process's own
`os.environ`) spawns fine. So the implemented pre-check searches this process's
own `os.environ.get("PATH", os.defpath)` unconditionally, ignoring `env`
entirely -- this is what actually predicts the real spawn below, on every
platform measured. Both docstrings (`spawn`, `SpawnError`) state this
corrected mechanism and name the measurement.

Checked every production `spawn()` call site for exposure to the now-rejected
wrong mechanism: `presentation/drivers/bwrap.py`'s call passes no `env` at all
(unaffected). `infra/supervisor/link.py`'s call passes `env=_SUPERVISOR_ENV`,
where `_SUPERVISOR_ENV["PATH"]` is a snapshot of `os.environ["PATH"]` taken at
import time -- in production these are normally equal, so the wrong mechanism
would rarely have misfired there, but the corrected implementation removes the
dependency on that coincidence entirely by consulting the real `os.environ` at
call time, same as the OS itself does.

### Changes
- `src/brig/infra/processes.py`: added `shutil.which` import; `spawn()` now
  pre-checks `argv[0]` against `os.environ.get("PATH", os.defpath)` before
  calling `os.posix_spawnp`, raising `SpawnError(argv, errno=errno.ENOENT)` when
  it can't resolve. Rewrote `spawn()`'s and `SpawnError`'s docstrings to state
  the real, narrowed guarantee and the residual Linux TOCTOU race honestly.
- `tests/e2e/test_processes_gateway.py`: six new tests -- unresolvable bare name
  raises (both platforms now); resolvable bare name unaffected; direct path
  (`/`) bypasses PATH search either way; `env`'s own narrower PATH does NOT
  make the pre-check raise for a name on this process's real PATH; a name
  resolvable only through `env`'s PATH DOES raise (this is the Linux-reproducing
  proof -- confirmed in the container to be exactly `32512 == 127<<8` without
  the fix).

### Proof
- `just lint`, `just typecheck`, `just gates`, `just done` all green on macOS
  (Darwin 27).
- Full suite (`tests/unit tests/integration tests/e2e`) run for real in a fresh
  privileged `ubuntu:24.04`/amd64 container with real `bwrap` 0.9.0
  (`brig-probe-amd64:latest`): 95 passed, 3 skipped (pre-existing, unrelated
  thread-safety skips), 0 failed -- nothing from TASK-0013's restructuring
  regressed.
- Confirmed in that same container: a raw `os.posix_spawnp('definitely-not-real-xyz', ...)`
  still does not raise and the child still exits 127 (`status=32512`) -- the
  original bug reproduces unchanged outside `spawn()`'s own pre-check. Against
  `spawn()` itself, the same shape now raises `SpawnError` (test passed above).

### Residual gap (named honestly, not closed)
The TOCTOU race between the pre-check and the real spawn is unchanged: on
Linux, nothing raises if `argv[0]` vanishes in that window, and the child still
exits 127 unexplained. On macOS the OS's own raise still covers it. This matches
the plan's own accepted-residual framing in AC#2's decision.

Both ACs hold and are checked. Status left In Progress per instructions --
review/close left to the reviewer.

Check `uv run just done` exited 0

(203 earlier lines omitted)
```text
[2m20:57:30.318[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m20:57:30.318[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m20:57:30.318[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m20:57:30.319[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m20:57:30.323[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m20:57:30.582[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 271ms
[2m20:57:30.585[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m20:57:30.586[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 486ms[39m[0m

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
INFO    -  Documentation built in 1.70 seconds

== architecture validate: PASS ==
[2m20:57:31.289[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m20:57:31.292[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m20:57:31.301[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m20:57:31.301[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m20:57:31.420[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m20:57:31.501[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m20:57:31.502[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 213ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

test append probe

(the stray line above is a reviewer tooling probe, not content)

## Review (reviewer, not the implementer)

Verdict: NOT closed. Left In Progress. The behaviour change is correct and the
central correction to the plan is independently reproduced -- but the change
lands two fresh measured-false claims about Linux into the very docstrings this
task exists to make true about Linux. To be corrected inside TASK-0014; no
drafts filed.

### Independently verified (all of it holds)
- **The PATH-source correction is real.** Reproduced from scratch, not trusted.
  macOS (CPython 3.15, Darwin 27): a name resolvable ONLY through env's PATH
  gives FileNotFoundError (posix_spawnp did NOT look there); a name resolvable
  ONLY through os.environ's PATH, with env={'PATH': '/definitely/not/real'},
  spawns and exits 0. Linux/glibc 2.39 (brig-probe-amd64:latest, amd64): the
  same two cases give NORAISE status 32512 (127<<8), and NORAISE status 0.
  os.posix_spawnp's own PATH search consults the CALLING process's os.environ,
  never the env argument, on both libcs. The plan was wrong; the implementation
  is right.
- **Control flow.** The pre-check is the second statement in spawn(), before
  _resolve_fd_sources and before any spawn, so it raises with no fds duplicated
  or leaked. It uses os.environ.get('PATH', os.defpath), not env, and raises
  SpawnError(argv, errno=errno.ENOENT).
- **The two PATH-divergence tests genuinely discriminate, in opposite
  directions**, against a naive search-env's-PATH implementation. The
  ignores_envs_own_narrower_path one: a naive implementation resolves nothing,
  raises, and the test expecting success fails. The
  raises_for_a_name_only_envs_own_path_would_resolve one: a naive
  implementation finds the probe in bin_dir, does not raise, and pytest.raises
  fails. This pair would have caught the plan's own error.
<!-- SECTION:NOTES:END -->
