---
id: TASK-0037
title: Docstrings carry the history and the SPEC has fallen behind the code
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T04:33:00Z'
labels:
  - size-3
dependencies: []
modified_files:
  - src/brig/__init__.py
  - src/brig/domain/__init__.py
  - src/brig/domain/channels.py
  - src/brig/domain/claims.py
  - src/brig/domain/effects.py
  - src/brig/domain/grades.py
  - src/brig/domain/jail_types/__init__.py
  - src/brig/domain/jail_types/bwrap.py
  - src/brig/domain/operations.py
  - src/brig/domain/plan.py
  - src/brig/domain/policy/__init__.py
  - src/brig/domain/policy/env.py
  - src/brig/domain/policy/paths.py
  - src/brig/domain/policy/stdio.py
  - src/brig/domain/teardown.py
  - src/brig/infra/__init__.py
  - src/brig/infra/files.py
  - src/brig/infra/placeholders.py
  - src/brig/infra/processes.py
  - src/brig/infra/sockets.py
  - src/brig/infra/state_dir.py
  - src/brig/infra/supervisor/__init__.py
  - src/brig/infra/supervisor/assemble.py
  - src/brig/infra/supervisor/link.py
  - src/brig/infra/supervisor/program.py
  - src/brig/infra/supervisor/wire.py
  - src/brig/presentation/__init__.py
  - src/brig/presentation/api.py
  - src/brig/presentation/driver.py
  - src/brig/presentation/drivers/__init__.py
  - src/brig/presentation/drivers/bwrap.py
  - src/brig/presentation/errors.py
  - src/brig/presentation/jail.py
  - src/brig/presentation/ports.py
  - src/brig/presentation/report.py
  - tests/integration/fakes.py
  - tests/e2e/test_processes_gateway.py
  - docs/spec/index.md
  - docs/glossary.md
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. 3,203 of 5,583 source lines (57%) are docstrings, with about 330 TASK/decision references (`plan.py` is 82% docstring), much of it narrating history. Some is already false: `_AwaitSupervisorDone` is referenced and does not exist (`effects.py`, `wire.py`); `env.py` and `effects.py` say there is no `frozendict`, which is a builtin on 3.15.0b4, so rule 8 is broken on a false premise. `docs/spec/index.md` lists claims, grades, sockets, supervisor and report as reserved, not built, against rule 18. Dead weight alongside: `Spawn` and `Reap` are never constructed but keep their driver arms, three port methods and adapters alive; each of ProcessUnknown, SupervisorDoneUnknown and the readiness outcomes exists three times (infra, ports, domain); three classes are named `ChannelRefused` with two meanings (rule 12); `LiveSupervisors` keys a dict that never holds more than one entry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Docstrings state the contract; history lives on the board
- [x] #2 The SPEC describes what is built, and frozendict replaces the dict workarounds
- [x] #3 The unused effects and their ports are gone, and one name means one thing
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Measured at the start (worktree of claude/embedder-gaps, 37cb619): src/brig is 6,310 lines, 2,976 of them module/class/function docstrings (47%, an ast count), 323 TASK/DRAFT/decision references.

### Order of work

1. **Dead code.** Remove the `Spawn` and `Reap` effects (`domain/effects.py`) and their arms in `presentation/driver.py`; `ProcessPort.spawn`, `.reap`, `.reap_deadline` (`presentation/ports.py`) and their adapters in `presentation/jail.py` (`_reap`, `_reap_deadline`, `_RealProcesses.spawn/reap/reap_deadline`); `infra/processes.reap_deadline`, whose only caller was that adapter, with its two gateway tests in `tests/e2e/test_processes_gateway.py`; and in `tests/integration/fakes.py` `FakeProcesses.spawn/reap/reap_deadline` with the fields only they set (`expires`, `spawned`, `spawned_inheritable_fds`, `reaped`, `reaped_deadline`) and the assertions on them. Kept, because something else uses them (each checked by grep): `infra.processes.spawn`/`SpawnError` (link.py starts the supervisor with it), `infra.processes.reap` (e2e tests reap the processes they spawn), `_ProcessIdentity` (`SupervisorPort.start`), `JailSpawnFailed` (`StartSupervisedCommand`), `ExitCodeUnknown`, `Deadline`.
2. **One name, one meaning.** `domain/channels.ChannelRefused` (a name refused) becomes `ChannelNameRefusal`; the readiness refusal keeps `ChannelRefused`. Copies: ports' `ProcessUnknown` and `SupervisorDoneUnknown` go; `ProcessPort.peek` returns `int | None | ExitCodeUnknown` and `SupervisorPort.await_done` returns domain's `ExitOutcome`, so `jail.py`'s wiring translates infra's sentinel straight into domain's and the driver translates nothing; `brig` exports `ExitCodeUnknown` in their place. Kept: infra's `ProcessUnknown`, `SupervisorDoneUnknown` and readiness values (infra imports no brig type, rule 1); ports' readiness outcomes (`ChannelReady`, `ChannelNotReady`, `ChannelRefused`, `ChannelReadinessRefusal`), the embedder-facing values, which domain has no copy of.
3. **frozendict** (rule 8). `Plan.env`, `StartSupervisedCommand.env`, `compile_run`'s and `create_bwrap_jail`'s `env`, `scrub_env`'s result, `grade` and `bwrap.ceilings`' results, `Jail.report`, and domain's module-level mappings become `frozendict`; `SupervisorPort.start` takes the frozendict; infra's `start` takes a `Mapping`. The false "no frozendict" statements go.
4. **`LiveSupervisors`** becomes `LiveSupervisor`, holding the one `Supervisor` its jail started (one instance per jail since TASK-0001.21); `await_done`/`close` on any other pid answer as for a closed one, so the port contract is unchanged.
5. **Docstrings.** Every module and function docstring in `src/brig` cut to its contract: what it does, its arguments, what it raises; history moves out (the board has it); measured facts a reader needs to not break something stay, one or two sentences, with their task or decision number. Code unchanged except steps 1-4. Test docstrings touched only where they name removed things.
6. **SPEC and glossary.** `docs/spec/index.md`'s Domain, Infra and Presentation sections describe what is built (files, sockets, state_dir, placeholders, supervisor, report) and drop removed behaviour; the ten laws section is untouched. `docs/glossary.md`'s effect, step, plan and jail entries stop naming `Spawn`/`Reap`.

### Risks

- A docstring cut that drops a measured fact a later change relies on (posix_spawn `EBADF` on a closed fd, the in-jail PID 1 vs bwrap's namespace, `--as-pid-1`, `setsid` compiled out of uv's CPython, ENOPROTOOPT vs EINVAL). Mitigation: each kept as one sentence with its number.
- Changing behaviour while editing text: mitigated by rewriting docstrings only, diffing code lines (`git diff` filtered to non-docstring lines) before commit, and the full suite.
- frozendict at a boundary that `json`, `posix_spawnp` or a test compares: frozendict equals the dict of the same items; infra converts with `dict(...)` where it already did.
- pypeeker `over-exposed-module-symbol` / `under-exposed-access` after renames and removals (e.g. infra `reap` left with only test callers): `just gates` decides.

### Proof

- `uv run just done` green: ruff, mypy strict, every pypeeker rule, the pypeeker rule tests, unit, integration twice, e2e, docs build, architecture lint.
- `grep` finds no `Spawn(`, `Reap(`, `reap_deadline`, `ProcessUnknown` outside infra and its tests, `SupervisorDoneUnknown` outside infra, `LiveSupervisors`, or "frozendict ... does not exist" in src.
- The ast count of docstring lines before and after, reported with the source line count.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Worker's report (@claude, 2026-11-03)

Commit 1d8e862 on claude/docs-drift (one commit; the board's own auto-commits sit around it). `uv run just done`: all steps passed.

**Measured** (ast count of module/class/function/attribute docstrings in `src/brig`): 6,310 -> 3,984 source lines; 2,976 -> 980 docstring lines (47% -> 25%); TASK/DRAFT/decision references 323 -> 127. A code-only diff (docstrings stripped, `ast.unparse`) shows only the changes below.

**#3 Dead code, one name one meaning.**
- Removed `Spawn`, `Reap`, their driver arms, `ProcessPort.spawn/reap/reap_deadline`, `jail.py`'s `_reap`/`_reap_deadline` and the `_RealProcesses` fields, `infra.processes.reap_deadline` (its only caller was that adapter) with its two gateway tests, and `FakeProcesses.spawn/reap/reap_deadline` with `expires`, `next_pid`, `spawned*`, `reaped*` and the assertions on them. Kept, each checked by grep: `infra.processes.spawn`/`SpawnError` (link.py), `infra.processes.reap` (e2e tests reap what they spawn), `_ProcessIdentity` (`SupervisorPort.start`), `JailSpawnFailed`. `SpawnedProcess` lost its last outside caller and became `_SpawnedProcess` (pypeeker demote).
- `domain/channels.ChannelRefused` -> `ChannelNameRefusal`; the readiness refusal keeps `ChannelRefused`.
- Copies: `ports.ProcessUnknown` and `ports.SupervisorDoneUnknown` are gone. `ProcessPort.peek` returns `int | None | ExitCodeUnknown`, `SupervisorPort.await_done` returns `ExitOutcome`; `jail.py`'s wiring translates infra's sentinel straight into domain's, and the driver translates nothing. `brig` exports `ExitCodeUnknown` in their place. Kept: infra's `ProcessUnknown`, `SupervisorDoneUnknown` and readiness values (rule 1: infra imports no brig type); the ports' readiness outcomes, which are the embedder-facing values and have no domain copy.

**#2 frozendict and the SPEC.** `Plan.env`, `StartSupervisedCommand.env`, `scrub_env`, `compile_run`/`create_bwrap_jail`'s `env` (now a `Mapping`), `grade`, `ceilings`, `Jail.report`, `_STRENGTH`, `_RANK` and the driver's `_SIGNALS` are `frozendict`; the false "no frozendict" statements are gone. `docs/spec/index.md`'s Domain, Infra and Presentation sections list what is built (files, state_dir, placeholders, sockets, supervisor, report) and what is not; the ten laws are untouched. `docs/glossary.md`'s effect, step, plan, process, jail and driver entries corrected.

**`LiveSupervisors` -> `LiveSupervisor`**, holding the one supervisor its jail started; any other pid answers as a closed one, so the port contract is unchanged.

**#1 Docstrings** in src cut to their contract; measured facts kept briefly with their numbers (EBADF on a CLOSE of a closed fd, `--as-pid-1` and PID 3, `setsid` compiled out of uv's CPython, bwrap's namespace being the host's, ENOPROTOOPT vs EINVAL, macOS EPERM from killpg, posix_spawnp searching the caller's PATH). Test docstrings changed only where they named removed things.

**Beyond the brief, flagged for review.**
- `JailExitUnknown`'s message said "already reaped elsewhere"; it now comes only from a lost supervisor report, so it reads "jail's exit code was lost before it was reported".
- `tests/e2e/test_report_battery.py` assigned to `os.environ`, which `brig-no-patching` reported on the base branch too (the gate was red before this task); it now passes the candidate env as a mapping.

**Not done, left for a follow-up:** `docs/architecture` (the LikeC4 model) still marks the supervisor "planned, not built"; it is outside the SPEC this task covers.

Check `uv run just done` exited 0

(264 earlier lines omitted)
```text
[2m04:33:13.394[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:33:13.427[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:33:13.442[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m04:33:15.783[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.53s
[2m04:33:15.786[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-docs/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:33:15.790[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.3s[39m[0m

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
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

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
INFO    -  Building documentation to directory: /home/user/brig-docs/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-docs/docs
INFO    -  Documentation built in 6.39 seconds

== architecture validate: PASS ==
[2m04:33:17.534[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:33:17.551[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-docs/docs/architecture[0m
[2m04:33:17.591[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:33:17.592[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:33:18.116[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m04:33:18.347[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m04:33:18.347[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 814ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
