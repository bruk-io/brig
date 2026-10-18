---
id: TASK-0012
title: >-
  A create_bwrap_jail failure after the supervisor script is written leaks it
  forever
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 16:16'
updated_date: '2026-10-18 17:27'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - src/brig/presentation/api.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
--------------------------------------------------
TASK-0001.21 ties supervisor-script cleanup to destroy_jail's own GroupState.GONE verification, which presupposes a Jail was returned to carry the file's path. If create_bwrap_jail's own run() raises (e.g. JailSpawnFailed, measured concretely on this macOS host: bwrap itself fails to spawn with FileNotFoundError since bwrap isn't installed here) AFTER _supervisors_for has already written the fresh supervisor script but BEFORE a Jail is ever constructed and returned, nothing ever deletes that file -- no Jail exists for any later destroy_jail call to act on. Confirmed not hypothetical: 22 such orphan files (35K each) were found already sitting in this host's real ~/.brig, consistent with this exact path having been hit repeatedly by prior test/agent activity on a bwrap-less macOS host this session. Candidate fix: wrap the write+spawn in a try that deletes the just-written file on any exception before it propagates, inside _supervisors_for or create_bwrap_jail itself, rather than only at the Jail-carries-it-to-destroy_jail stage.

Second shape, found reviewing TASK-0001.21's own close: destroy_jail deletes the script only after confirming GroupState.GONE -- a teardown that never reaches that (raises JailTeardownFailed, the kill ladder's last verify still found the group alive) leaks the script permanently too, with nothing to sweep it. Same unswept-file family as the create-time-failure shape above, different trigger.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A create_bwrap_jail call whose own run() raises before returning a Jail does not leave its freshly-written supervisor script behind
- [x] #2 A test reproduces this exact shape (a failing supervisor spawn, e.g. via a fake/fixture that fails after the script write) and asserts the file is gone
- [x] #3 A destroy_jail call that raises JailTeardownFailed (the kill ladder's last verify still found the group alive) does not leave the jail's own supervisor script behind either, or a decision record says why that shape stays accepted
- [x] #4 A test reproduces the JailTeardownFailed shape and asserts on the chosen outcome
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. In `_supervisors_for`/`create_bwrap_jail`'s flow, wrap the write-then-use
   sequence so the just-written supervisor script is deleted on any exception
   that would otherwise propagate before a `Jail` is ever constructed and
   returned (covers both named shapes: create_bwrap_jail's own run() raising
   JailSpawnFailed, and a destroy_jail that raises JailTeardownFailed without
   ever reaching GroupState.GONE -- the second needs its own try/except around
   the teardown-failure path in destroy_jail, deleting the script on that
   failure too, since no later call will ever get another chance).
2. Tests for both shapes: a fake/fixture that fails the supervisor spawn after
   the script write (asserts the file is gone); a fixture that makes teardown
   never reach GroupState.GONE (asserts the file is gone despite
   JailTeardownFailed being raised).

### Proof
- just gates, just typecheck, just done green.
- Real Linux + bwrap (brig-probe-amd64:latest): confirm no leftover file in a
  fresh BRIG_HOME after deliberately forcing both failure shapes.

### Risks
- Don't let cleanup-on-failure mask or swallow the real exception an embedder
  needs to see (JailSpawnFailed/JailTeardownFailed must still propagate) --
  the file deletion is a side effect alongside the raise, never a replacement
  for it.
- JailTeardownFailed's own case: deleting the script while the jail's group
  might still genuinely be alive (that's exactly what the failure means) is
  still safe for the SAME reason TASK-0001.21's design relies on -- the file
  itself doesn't need the process alive, only not-yet-execed-when-deleted, and
  by this point it was already exec'd (if it ever would be) long before
  teardown started. State that reasoning explicitly rather than leaving it
  implicit, since it's the one subtle part of this task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented both fixes in src/brig/presentation/api.py:
- create_bwrap_jail: wraps run(operations.create(...)) in try/except BaseException,
  deleting supervisor_script (if one was written) before re-raising unchanged.
  Catches BaseException rather than naming JailSpawnFailed specifically, so a future
  failure added to that call site is never a second leak to rediscover.
- destroy_jail: moved the supervisor_script deletion to run unconditionally after
  teardown's own verify (right after supervisors.close), before the
  `if state is not GroupState.GONE: raise JailTeardownFailed` check -- so it now runs
  whether or not GONE was reached. Docstring states explicitly why this is still safe:
  the file only ever needed to survive until it was exec'd, never while a process
  still runs from it, and by the time teardown's own verify has run at all, any exec
  that was ever going to happen already happened.

Deliberately did NOT wrap destroy_jail's own `run(operations.destroy(jail.process), ...)`
call the same way: operations.destroy only yields Verify/SignalGroup effects, and
presentation/drivers/bwrap.py's own docstring documents both as never raising (their
ports hand back sentinels, not exceptions) -- unlike Spawn/StartSupervisedCommand,
neither arm is wrapped in the driver. The task's own two named shapes don't include
this, so left as-is; flagging in case a future ProcessPort violating that contract
ever needs it wrapped too.

Tests added:
- tests/e2e/test_supervisor_script_cleanup.py: new test for AC#1/#2, skipif bwrap IS
  installed (inverse of this file's other tests) -- reproduces the exact real,
  measured macOS shape (bwrap missing -> JailSpawnFailed before a Jail is ever
  returned) rather than an engineered one. Tried engineering a portable, bwrap-
  presence-independent repro first (starving PATH so posix_spawnp can't find "bwrap")
  and confirmed on macOS, but it does NOT reproduce on Linux: measured in
  brig-probe-amd64:latest that os.posix_spawnp falls back to running the unresolved
  command through `/bin/sh -c` rather than raising FileNotFoundError, so the "real
  world" difference is genuine, not a test artifact -- infra/processes.py's own
  SpawnError docstring ("argv[0] could not be found on PATH") does not hold on Linux,
  worth its own follow-up task. Settled on the inverse-skipif e2e test instead,
  matching this repo's own convention for host-shape-dependent reality.
- tests/integration/test_teardown_failure_deletes_script.py: new test for AC#3/#4,
  Jail built through create_bwrap_jail against fakes then supervisor_script replaced
  with a real on-disk file (dataclasses.replace), FakeProcesses(alive=True) forcing
  JailTeardownFailed; asserts the file is gone and the exception still propagates.

Proof:
- just gates / just typecheck / just lint / just done: all green on macOS (recorded
  above via record-check --tier full).
- Real verification in brig-probe-amd64:latest (ubuntu:24.04 amd64, --privileged, real
  bwrap present), repo copied to /work, fresh BRIG_HOME, uv sync:
  - just gates, just typecheck, just check (unit+integration x2), full tests/e2e
    suite: all green (51 passed, 3 skipped for unrelated, already-documented reasons).
  - tests/e2e/test_supervisor_script_cleanup.py's new AC#1/#2 test SKIPPED there, as
    designed (bwrap is present in that container, so the shape it proves cannot occur
    there) -- so AC#1's own fix was verified separately with a throwaway (uncommitted)
    script run via `uv run python3 -c ...` that calls the real create_bwrap_jail with
    api.run monkeypatched to raise after the real _supervisors_for has already written
    a real script file: confirmed 0 files in the state dir before, 0 after, with the
    original RuntimeError propagating unchanged. Monkeypatching here is fine since it
    is a throwaway diagnostic, never committed, and outside anything pypeeker gates.
  - tests/integration/test_teardown_failure_deletes_script.py (AC#3/#4): passed for
    real in the container too (fakes-based, so bwrap's presence doesn't matter there).

Side finding, not fixed here: infra/processes.py's spawn() docstring says SpawnError
covers "argv[0] could not be found on PATH" -- measured false on Linux (glibc's
posix_spawnp falls back to /bin/sh -c instead of raising ENOENT when a bare command
name resolves nowhere on PATH; confirmed in brig-probe-amd64:latest). Worth a follow-up
task to correct that docstring claim and/or decide whether brig needs to detect this
shell-fallback-exit-127 case explicitly.

Status left as In Progress per the assigning message; ACs #1-4 ticked since they
genuinely hold.

Check `uv run just done` exited 0

(203 earlier lines omitted)
```text
[2m17:27:43.283[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m17:27:43.283[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m17:27:43.284[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m17:27:43.284[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m17:27:43.289[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m17:27:43.554[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 278ms
[2m17:27:43.557[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m17:27:43.557[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 498ms[39m[0m

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
INFO    -  Documentation built in 1.50 seconds

== architecture validate: PASS ==
[2m17:27:44.240[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m17:27:44.244[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m17:27:44.253[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m17:27:44.253[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m17:27:44.371[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m17:27:44.453[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m17:27:44.453[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 213ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```
<!-- SECTION:NOTES:END -->
