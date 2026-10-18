---
id: TASK-0006
title: >-
  The supervisor's temp script lives in /tmp, so any fs policy that excludes
  /tmp breaks every jail under it
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 13:05'
updated_date: '2026-10-18 13:36'
labels:
  - brig
  - size-3
dependencies: []
modified_files:
  - src/brig/infra/state_dir.py
  - src/brig/presentation/api.py
  - src/brig/domain/jail_types/bwrap.py
  - tests/e2e/test_fs_policy_battery.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while reviewing TASK-0001.20 (a dev-dependency change that could not have caused it; confirmed pre-existing against a clean git baseline).

tests/e2e/test_fs_policy_battery.py::test_a_path_outside_the_policy_is_unreadable_in_a_real_bwrap_jail fails DETERMINISTICALLY on real Linux (ubuntu:24.04 amd64, --privileged): 5 runs out of 5, identical node id. 3 runs with TASK-0001.20's diff applied, 2 runs with pyproject.toml/uv.lock reverted to the committed baseline. Same failure both arms, so it is pre-existing and unrelated to that task.

This is NOT container flakiness, NOT a reap race, and NOT related to bwrap-in-container or posix_spawn/setsid (TASK-0001.20's implementation notes characterised it that way; that characterisation is wrong on every count and is corrected here).

Root cause: presentation/api.py:108 writes the assembled supervisor to a tempfile.NamedTemporaryFile with prefix 'brig-supervisor-' -- i.e. into /tmp. The test deliberately builds a policy via _mirror_policy_excluding('tmp') to prove a path outside the allow-list is ENOENT inside the jail. That policy also unbinds the supervisor's own script, so the jail's PID 1 never starts:

  /work/.venv/bin/python: can't open file '/tmp/brig-supervisor-XXXX.py': [Errno 2] No such file or directory

which surfaces as ExitCodeUnknown -> JailExitUnknown(Process(pid=..., pgid=...)) from api.py:331, instead of the expected probe exit code 2.

So the supervisor mechanism (TASK-0001.15 / TASK-0004) has an undeclared dependency on /tmp being bound, which TASK-0001.16's narrowed-policy feature can silently revoke. Any embedder passing a policy that does not bind /tmp gets a jail that cannot start at all.

Invisible on macOS: the test is skipif(shutil.which('bwrap') is None), so it skips there and the whole suite looks green. It would fail on the first real CI run on Linux.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The supervisor's script is reachable from inside the jail regardless of the caller's fs policy (e.g. the supervisor's own path is bound into the launch unconditionally, or the script is passed by a mechanism that does not depend on the policy's binds)
- [ ] #2 tests/e2e/test_fs_policy_battery.py::test_a_path_outside_the_policy_is_unreadable_in_a_real_bwrap_jail passes on real Linux, exiting 2 (ENOENT for the planted secret) rather than raising JailExitUnknown
- [ ] #3 A policy that excludes /tmp is covered by a test asserting the jail still starts, so this coupling cannot regress silently
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Design (settled with the owner)
A dedicated home-dir folder for brig's own runtime artifacts, not /tmp: default
`~/.brig`, overridable in full via `BRIG_HOME` (when set, taken exactly as given,
no further default-resolution logic). The supervisor's assembled script moves there.
That directory is bound into every bwrap launch unconditionally -- it is brig's own
structural requirement, not part of the caller's FsPolicy, the same way
`_NAMESPACE_FLAGS`/`_INHERITABLE_FDS` are structural rather than policy-controlled.

### Order of work
1. New `src/brig/infra/state_dir.py`: `resolve(env: Mapping[str, str] = os.environ) ->
   Path` (pure: `BRIG_HOME` if set, else `Path.home() / ".brig"`) and `ensure(path:
   Path) -> Path` (the one I/O call, `mkdir(parents=True, exist_ok=True)`) -- kept
   separate per functional-core/imperative-shell.
2. `src/brig/presentation/api.py`'s `_supervisor_path()`: write the assembled
   supervisor file inside `state_dir.ensure(state_dir.resolve())` (via
   `tempfile.NamedTemporaryFile`'s `dir=` parameter, keeping its collision-safe
   random suffix) instead of the default tempdir (`/tmp`).
3. `src/brig/domain/jail_types/bwrap.py`'s `compile_supervisor_launch`: take the
   resolved state directory as a new plain-string parameter (domain does no I/O to
   locate it, rule 2 -- presentation resolves it and hands it in, the same pattern
   `supervisor_path` already uses) and add one unconditional `--ro-bind
   <state_dir> <state_dir>`, placed after the policy's own binds so it cannot be
   shadowed by one of them, before `_NAMESPACE_FLAGS`.
4. Update every caller (`_supervisor_argv`, `_supervisors_for`) to pass the resolved
   directory through.
5. Tests: `state_dir.resolve()` honors `BRIG_HOME` when set and defaults to
   `~/.brig` otherwise (unit-level, pure, synthetic env mappings, no real I/O);
   `tests/e2e/test_fs_policy_battery.py::test_a_path_outside_the_policy_is_unreadable_in_a_real_bwrap_jail`
   passes on real Linux, exiting 2 rather than raising `JailExitUnknown`; a new e2e
   test asserting a policy that excludes /tmp (the exact shape that broke this) still
   lets the jail start, so this coupling cannot regress silently.

### Proof
- just gates, just typecheck, just done green.
- Real Linux + bwrap (brig-probe-amd64:latest): the fs-policy battery's previously
  failing test now passes; the new /tmp-excluded-policy test passes.

### Risks
- The unconditional bind must land in the compiled argv in a position bwrap actually
  honors over a conflicting policy bind (bwrap applies binds in argv order; later
  wins on overlapping paths) -- verify this empirically against real bwrap, not just
  by reading the flag order.
- `BRIG_HOME` is a brig-internal operational setting, never routed through
  `EnvPolicy` scrubbing (that governs what the *jailed command* sees, not brig's own
  host-side config) -- make sure nothing conflates the two.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Check `uv run just done` exited 0

(193 earlier lines omitted)
```text
[2m13:36:52.518[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m13:36:52.518[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m13:36:52.518[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m13:36:52.519[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m13:36:52.523[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m13:36:52.802[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 291ms
[2m13:36:52.804[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m13:36:52.805[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 502ms[39m[0m

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
[2m13:36:53.751[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m13:36:53.755[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m13:36:53.763[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m13:36:53.764[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m13:36:53.878[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m13:36:53.960[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m13:36:53.960[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 209ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```
<!-- SECTION:NOTES:END -->
