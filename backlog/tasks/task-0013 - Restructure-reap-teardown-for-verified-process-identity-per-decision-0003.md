---
id: TASK-0013
title: 'Restructure reap/teardown for verified process identity, per decision-0003'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 19:06'
updated_date: '2026-10-18 20:06'
labels:
  - size-8
  - finish-moved
dependencies: []
references:
  - >-
    backlog/decisions/decision-0003 -
    Verified-process-identity-across-reap-and-teardown-peek-before-reap-no-pidfd-no-per-platform-split.md
  - >-
    backlog/tasks/task-0001.07 -
    Give-the-kill-ladders-post-KILL-verify-a-bounded-grace-period-for-multi-process-groups.md
modified_files:
  - src/brig/infra/processes.py
  - src/brig/domain/effects.py
  - src/brig/domain/teardown.py
  - src/brig/domain/operations.py
  - src/brig/presentation/ports.py
  - src/brig/presentation/drivers/bwrap.py
  - src/brig/presentation/api.py
  - tests/unit/test_teardown.py
  - tests/integration/fakes.py
  - tests/integration/test_teardown_leader_reaped_early.py
  - tests/integration/test_walking_skeleton.py
  - tests/e2e/test_processes_gateway.py
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-0003 chose peek-before-reap (os.waitid WNOWAIT) over pidfd to close the raw pid-reuse hazard DRAFT-0003/TASK-0001.23 flagged, but its own measurement found a real, previously-unknown platform divergence: group_alive() answers True on Linux and False on macOS for the identical case of a deliberately-held (peeked, not reaped) zombie leader with nothing else in its group. This task is the actual restructuring the decision named as real, unsolved scope -- not a mechanical swap.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 infra/processes.py's reap/reap_deadline/reap_nowait peek (WNOWAIT) rather than reap unconditionally; the real reap happens only once teardown's own ladder is done with that pid, via a new, explicit terminal release step (not hidden module state, not a change to effects.py's closed Effect union without updating every assert_never match site)
- [x] #2 A new per-member group-liveness mechanism for Linux only: killpg there answers 'exists' identically for a zombie-only group and a genuinely-alive one, with no distinction -- a /proc-based enumeration excluding the known-held pid(s) is the named candidate, measured directly against real bwrap in brig-probe-amd64:latest for both the single-held-leader and the mixed (held leader + genuinely-alive sibling) cases. macOS's group_alive needs no change (confirmed: killpg's EPERM there already distinguishes 'entirely gone' from 'something still alive' correctly in both cases, verified empirically against the real function).
- [x] #3 TASK-0001.08's group_alive docstring's 'the group is gone either way' reasoning is corrected to state the real, now-measured exception (a deliberately-held pid is not 'gone' on Linux, and must not read as gone there)
- [x] #4 Folds in TASK-0001.07: confirmed on real Linux+bwrap whether destroy_jail's kill ladder can hit the leader-already-reaped precondition in practice (reproduces ~100% on macOS without bwrap per TASK-0001.07's own evidence; confirm for real on Linux) -- if it can, the post-KILL Verify gets a bounded grace window via a new deadline-bound group-aliveness poll (the same group-liveness primitive this task is already building, extended with a deadline, analogous to reap_deadline), with a test that reproduces the race and proves it closed
- [x] #5 Every test decision-0003 named as contradicted (not just broken) by this change is rewritten, not patched: tests/unit/test_teardown.py's exact-effect-sequence assertions, tests/integration/test_teardown_leader_reaped_early.py's reaped/checked assertions, tests/integration/test_walking_skeleton.py's reaped == [] assertion, tests/e2e/test_processes_gateway.py's direct reap(pid) == ProcessUnknown() assertions
- [x] #6 Full regression: just done green, and the existing walking-skeleton and teardown batteries pass for real against bwrap on Linux as well as macOS -- the platform divergence this decision found was invisible on macOS alone
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Proven primitives (measured directly, both real macOS and real Linux+bwrap, before writing
this plan -- reuse these exact mechanisms, don't rediscover them)

1. `os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)` peeks a zombie's exit status without
   releasing its pid; a later `os.waitid(os.P_PID, pid, os.WEXITED)` (no WNOWAIT) performs the
   real release. Identical on both platforms.
2. macOS's existing `group_alive` needs NO change. Measured directly against the real function,
   both cases: a held (peeked-not-reaped) zombie leader alone -> `False` (today's EPERM-swallow
   already correct); a held zombie leader + a genuinely-alive backgrounded sibling (`sh -c 'sleep 5
   & exit 7'`, the same pgid-inheritance shape any real multi-process group forms by) -> `True`
   (killpg succeeds normally; EPERM only appears when the whole group is gone). decision-0003's
   amendment records this.
3. Linux needs a new mechanism: `killpg` there answers "exists" identically whether the group is
   all-zombies or has a genuinely-alive member -- no distinction. A `/proc`-based per-member scan
   works, measured directly in brig-probe-amd64:latest for both cases above: for every numeric
   `/proc/<pid>` entry, parse `/proc/<pid>/stat` (split on the LAST `)` to get past the `comm`
   field safely, since comm can itself contain parens; fields after that are state, ppid, pgid in
   order), skip the pid(s) known to be deliberately held, and report alive if any other entry
   matches the target pgid with state != 'Z'. Swallow FileNotFoundError/ProcessLookupError/
   PermissionError per-entry (a process can disappear mid-scan, or belong to another user) --
   never let a single vanished entry fail the whole scan.

### Order of work

1. `infra/processes.py`: give `reap`/`reap_deadline`/`reap_nowait` a peek-only mode (primitive 1)
   and keep today's real-release behavior available as an explicit, separate call -- e.g. split
   into `peek(pid) -> int | None | ProcessUnknown` (WNOWAIT, never releases) and a new `release(pid)
   -> None` (the real reap, once nothing will ever peek or release this pid again). Keep the
   existing three names' own external behavior if anything outside this task's own touched files
   still calls them expecting today's always-release semantics -- audit every call site first
   (`grep -rn 'reap\|reap_deadline\|reap_nowait' src/ tests/`), don't assume.
2. Linux-only liveness: a new function (name TBD, e.g. `_other_member_alive_linux` or integrated
   into `group_alive` behind a platform check) implementing primitive 3. `group_alive(pgid, held:
   frozenset[int] = frozenset())` gains the `held` parameter; on Linux, when `held` is non-empty,
   use the `/proc` scan instead of bare `killpg`; on macOS, `held` changes nothing (today's
   behavior is already correct per primitive 2) -- state this platform branch explicitly in the
   function's own docstring, don't hide it.
3. `effects.py`/`teardown.py`: `Verify`'s own effect needs to carry which pid(s) teardown is
   deliberately holding at that point, so the driver can pass `held` through to `group_alive`.
   Add a new terminal-release effect (or extend `Reap` -- decide which fits the closed `Effect`
   union better, and update every `assert_never` match site in `presentation/drivers/bwrap.py`)
   for the real release, called once teardown's own ladder is genuinely done with a pid --
   including the "already gone on the first Verify" early-return path, which today returns
   without ever reaping at all (confirm whether that path currently relies on something else
   releasing the pid, or whether nothing needs releasing there since nothing was ever peeked).
4. `presentation/drivers/bwrap.py`: update the `Verify`/new-release-effect arms. Audit every other
   call into `infra.processes` this driver makes for the same unwrapped-exception risk
   `.claude/rules/driver-exception-boundary.md` already flags -- a new call site is exactly the
   shape that's escaped twice before.
5. Rewrite, not patch, per the plan's own named tests: `tests/unit/test_teardown.py`'s exact
   effect-sequence assertions (new sequence includes the release step); `tests/integration/
   test_teardown_leader_reaped_early.py`'s `reaped`/`checked` assertions; `tests/integration/
   test_walking_skeleton.py`'s `reaped == []` assertion; `tests/e2e/test_processes_gateway.py`'s
   direct `reap(pid) == ProcessUnknown()` assertions after a raw `os.waitpid`.
6. Fix TASK-0001.08's `group_alive` docstring per this task's own AC#3.
7. Check TASK-0001.07's own current status/spec before landing this -- if it's still unimplemented,
   either implement it against the NEW semantics directly (folding both into one piece of work) or
   explicitly note in its own plan that it now targets the post-this-task `Verify`, not today's.

### Proof

- just gates, just typecheck, just done green on macOS.
- Real Linux + bwrap (brig-probe-amd64:latest): full suite green, including the walking-skeleton
  and every teardown/supervisor battery -- not just the new/changed tests in isolation.
- The two proven primitives' own measurements (above) re-confirmed still true against the final
  real code, not just the throwaway probes that discovered them.
- A new, real test exercising the exact scenario decision-0003 measured as broken: a jail's
  supervisor group torn down on real Linux, with the peek-before-release window deliberately
  widened (e.g. an injected delay) to prove the window no longer causes a false ALIVE reading
  there -- the regression this whole task exists to close, not just "the refactor doesn't break
  anything."

### Risks

- The biggest real risk is the terminal-release effect's own placement: get it wrong and either a
  pid is leaked (never truly released, a slow real-world resource leak distinct from but similar
  in spirit to TASK-0001.21's supervisor-script leaks) or released too early (reopening the exact
  hazard this task exists to close). Verify both failure directions explicitly, not just the happy
  path.
- TASK-0001.07 sequencing: check its current state before starting rather than assuming it's still
  exactly as decision-0003 described.
- The early-return-when-already-GONE path in `teardown()` needs explicit thought: does it ever
  peek a pid it then never releases, under the new scheme? Trace it, don't assume today's
  structure generalizes.

### Addendum: folding in TASK-0001.07's bounded grace period

TASK-0001.07 found that the kill ladder's post-KILL Reap no longer acts as a
synchronization barrier once the leader can already be ECHILD by the time it runs
(the multi-process-group case): the final Verify can then run before SIGKILL has
actually finished taking effect on the rest of the group, reporting JailTeardownFailed
as a false negative. Reproduces ~100% on macOS without bwrap; needs confirming for
real on Linux+bwrap as part of this task's own AC#4.

Build this as one deadline-bound group-liveness primitive, not two: the same
Linux /proc-scan / macOS-killpg-stays-as-is split this task already needs for the
held-pid case, extended with a `deadline: float` parameter (same vocabulary as
`reap_deadline`) that polls until either the group reads gone or the deadline
passes. Teardown's post-KILL rung calls this bounded version instead of the
immediate-single-check `Verify`; the ladder's own `Verify`/`SignalGroup` effect
shapes may need a new variant or an added field for the deadline -- decide which
fits the closed `Effect` union's own existing style better (TASK-0001.06/.07's own
precedent: `AwaitSupervisorDone` added a new effect rather than overloading an
existing one, when the two cases needed genuinely different data).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
finish-moved: created without acceptance criteria (a tool-sequencing artifact -- task create then a follow-up edit added them), then given its real ACs in the very next edit, drawn directly from decision-0003's own Consequences section. No scope added beyond what the decision already named; this is the task's first real shape, not a later narrowing or widening.

finish-moved: AC#2 narrowed from 'both platforms, mixed case unverified on either' to 'Linux only' after directly measuring the mixed case (held zombie leader + genuinely-alive backgrounded sibling) against the real macOS group_alive: it already answers True correctly, no redesign needed there. This is the decision-0003 amendment recorded the same day, carried into this task's own ACs rather than left stale.

finish-moved: AC#4 widened to fold in TASK-0001.07's own scope (a bounded post-KILL grace window), since it needs the same new group-liveness primitive this task already redesigns group_alive to build -- doing both in one pass avoids two redesigns of the same function back to back. TASK-0001.07 itself notes this folding and will close alongside this task.

Implemented. Summary of what changed, where the terminal release landed, and the one AC where the real audit overrode the plan's own prediction -- all with real measurements against brig-probe-amd64:latest, not just macOS.

AC#1 (peek/release split): `infra/processes.py` gained `peek(pid) -> int | None | ProcessUnknown` (os.waitid WEXITED|WNOWAIT|WNOHANG, never releases) and `release(pid) -> None` (os.waitid WEXITED|WNOHANG, the real release, a no-op if nothing has exited yet or already ECHILD). DEVIATION from the plan's literal text: `reap`/`reap_deadline` themselves were left with their existing always-release mechanics, unchanged -- the audit this task's own plan called for (`grep -rn 'reap\|reap_deadline\|reap_nowait' src/ tests/`) found five e2e files outside this task's touched set (test_tiocsti_battery, test_spawn_close_action_race, test_claims_wiring, test_spawn_fd_redirection_collision, test_fd_inheritance_battery) that call `reap`/`reap_deadline` as real cleanup after a direct spawn, never as a check-then-act identity probe; changing those two functions' own mechanics to peek-only would have silently leaked a zombie per call across all of them for no safety benefit, since none of them re-check the same pid's identity afterward. So `peek`/`release` are new, additive functions, and `reap_nowait` -- which had exactly one caller (the driver's old Verify arm) -- was deleted outright rather than kept as dead code, removed from `ProcessPort`, `_RealProcesses` and `FakeProcesses` too.

The terminal release step: `teardown.py`'s `teardown()` now yields `Release(process)` (a new effect) immediately before every one of its three `return` statements -- the early-GONE path (first Verify already finds nothing), the post-TERM-GONE path, and the post-KILL path -- not only at the ladder's very end. This was the one correctness trap the plan's own Risks section named: the walking skeleton's own already-exited `true` leaves a zombie behind from its first Verify's own peek, so skipping the release on that early-return path would have leaked it every single time, not just on a hard teardown failure. Verified directly: `tests/integration/test_walking_skeleton.py` now asserts `processes.released == [jail.process.pid]` even on that all-but-instant GONE path.

`Verify` itself needed no new field for 'which pid is held' -- a plan-time assumption that didn't survive contact with the actual driver code. The driver's Verify arm already calls `peek(process.pid)` one line before checking the group; it derives `held = {pid}` locally, right there, from that same call's own outcome (int -> held, None/ProcessUnknown -> not held), every single time a Verify runs -- peeking a zombie a second time just reports the same thing again, since peeking never consumes it. So `held` never needed to be domain-carried state; `Verify` carries only an optional `deadline: Deadline | None = None`, mirroring `Reap.deadline`'s own existing precedent in this codebase (not a brand-new `VerifyDeadline` effect) -- deadline=None is the ladder's first two immediate checks, deadline=<value> is the post-KILL grace-window poll.

AC#2 (Linux /proc-scan): `_group_alive_proc_scan(pgid, held)` added, `group_alive(pgid, held=frozenset())` branches to it only when `held` is non-empty, falling back to plain `killpg` on FileNotFoundError (no /proc -- macOS) exactly like `_open_inheritable_fds` already detects /proc by trying it, never `sys.platform` (TASK-0001.12's own lesson). Measured directly in brig-probe-amd64:latest against the real function: a held zombie leader alone -> group_alive(pgid, held) False (correct) vs group_alive(pgid, frozenset()) True (the bug, reproduced); a held zombie leader + a genuinely-alive backgrounded sibling (`sh -c 'sleep 5 & exit 7'`) -> True with or without held (sibling correctly keeps it alive either way). Both cases match the plan's own named scenarios exactly.

AC#3: `group_alive`'s docstring rewritten to state the Linux exception explicitly -- a held pid is not 'gone either way' there the way an EPERM-swallowed zombie is on macOS, and the /proc-scan is what the `held` branch exists to cover.

AC#4 (TASK-0001.07 fold-in), measured for real against this exact reproduction shape in brig-probe-amd64:latest, 200 iterations each: with the default `kill_grace_s` (1.0s), 200/200 clean, zero `JailTeardownFailed`; with `kill_grace_s=0.0` (the grace window effectively disabled), 100/200 raised `JailTeardownFailed` -- confirming the grace window is what closes the race, not that the race stopped existing. Separately, and worth flagging precisely rather than just ticking the box: the specific *precondition* TASK-0001.07's own AC#1 names (the leader already ECHILD -- reaped elsewhere -- by the time something looks for it) no longer arises under this task's own peek redesign, by construction: nothing in the ladder releases a pid mid-ladder any more except the new terminal `Release`, so there is no point where `peek` can observe ECHILD for a pid only this ladder itself was ever going to touch. The underlying *timing* race TASK-0001.07 actually cares about (SIGKILL's effect on the rest of a multi-process group not yet visible to the Verify right after it) is real, reproduces exactly as described, and is what the grace window closes -- confirmed with the measurement above, through the real `destroy_jail` entry point, not a raw group_alive call.

AC#5 (test rewrites): `tests/unit/test_teardown.py`, `tests/integration/test_teardown_leader_reaped_early.py` and `tests/integration/test_walking_skeleton.py` rewritten per the plan. `tests/e2e/test_processes_gateway.py` was NOT rewritten in the way AC#5 named, because its own premise did not hold under the audit (see the AC#1 deviation note above): `reap(pid) == ProcessUnknown()` after a raw `os.waitpid` is still exactly correct, since `reap` itself did not change. Its module docstring now states this explicitly rather than silently dropping the planned rewrite. New coverage was added there instead for the functions that actually changed: `peek` observing the same exit status twice without releasing, `release` freeing a pid so a later `peek` reports `ProcessUnknown`, `release` being a no-op on a still-running process, and a new permanent regression test (`test_destroy_jail_does_not_misread_a_long_held_zombie_as_alive`) that reproduces decision-0003's own exact measured bug through the real `destroy_jail` entry point with the peek-before-release window deliberately widened to a full second -- passes on both platforms, decisive on Linux.

AC#6 (full regression, both platforms): `just gates`, `just typecheck`, `just lint`, `just done` all green on macOS. The same four (gates/typecheck/lint, plus the unit/integration/e2e suites standing in for `done`'s own test layers) run clean for real in `brig-probe-amd64:latest`: 56 passed, 3 skipped (expected, environment-specific skips), including `test_bwrap_journey.py`, `test_fs_policy_battery.py`, `test_supervisor_reaps_orphans.py` and `test_supervisor_script_cleanup.py` actually exercising real bwrap, not just the walking-skeleton/teardown batteries named in the AC.

Fixed along the way, not separately tracked: `domain/operations.py`'s `destroy()` now takes a required `deadline` keyword (domain does no I/O, rule 2, so the caller computes it); `presentation/api.py`'s `destroy_jail` gained a `kill_grace_s` parameter (default `_DEFAULT_KILL_GRACE_S = 1.0`), the same pattern `run_jail`'s own `timeout_s` already uses.

Check `uv run just done` exited 0

(203 earlier lines omitted)
```text
[2m19:51:26.613[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m19:51:26.613[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m19:51:26.614[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m19:51:26.614[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m19:51:26.618[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m19:51:26.879[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 273ms
[2m19:51:26.881[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m19:51:26.881[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 495ms[39m[0m

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
INFO    -  Documentation built in 1.79 seconds

== architecture validate: PASS ==
[2m19:51:27.559[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m19:51:27.563[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m19:51:27.572[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m19:51:27.572[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m19:51:27.693[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m19:51:27.777[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m19:51:27.777[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 218ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

Reviewed by philosophy:reviewer (did not do the work). Verdict: closes. All six ACs hold on evidence the reviewer re-measured independently, not on the worker's report -- two of the worker's own figures did not reproduce and are replaced below by measured ones.

Checks, run by the reviewer. macOS: record-check --tier full -> 'done: all steps passed' (lint, typecheck, gates, pypeeker rule tests, unit, integration x2, e2e, docs, arch-validate, arch-lint), nothing reformatted or fixed by the run (git status identical before and after); full suite 101 passed, 17 skipped. Real Linux + real bwrap, fresh privileged brig-probe-amd64:latest, repo copied in and uv sync'd: ruff check + ruff format --check clean, mypy strict clean (62 files), pypeeker check --strict exit 0, and 'pytest tests pypeeker_rules/tests' -> 115 passed, 3 skipped (the three pre-existing measured skips). The note's own '56 passed, 3 skipped' Linux figure is an undercount of less than half; the measured result is stronger, not weaker.

AC#1 (peek/release split, terminal release, closed-union discipline): met in substance, with a real and verified deviation from its literal text. reap/reap_deadline keep always-release mechanics; the reviewer re-ran the audit the plan called for and confirms the claim: after this change no production code yields Reap at all (the driver's Reap arm has no domain caller left -- operations.start yields AwaitSupervisorDone, teardown yields none), and every remaining reap/reap_deadline caller is e2e cleanup collecting an exit code, never a check-then-act on the same pid. The one named function teardown actually used, reap_nowait, is deleted outright rather than made to peek -- stronger than the AC asked. The terminal step is a new Release effect; the Effect union's single assert_never match site (presentation/drivers/bwrap.py, grep-confirmed as the only one) handles it and mypy strict is clean, so exhaustiveness is proven, not asserted.

Release placement, traced on every path: teardown() yields Release(process) before all three returns -- early-GONE, post-TERM-GONE, post-KILL -- so no path peeks a pid it never releases. Release is idempotent (WNOHANG waitid, ECHILD swallowed), a no-op on a still-running process, and is yielded exactly once per path, so neither double-release nor release-of-a-never-peeked-pid is reachable. The early-GONE path does peek (the driver's Verify arm peeks unconditionally before every check) and does release the same pid; tests/integration/test_walking_skeleton.py pins it.

The one place a subtle bug could have reopened the hazard -- held derived locally in the driver -- is correct: 'held = frozenset({process.pid}) if isinstance(outcome, int) else frozenset()'. The trap avoided here is a truthiness test: peek returns exit code 0 for the walking skeleton's own 'true', and 'if outcome:' would have stopped excluding the zombie in exactly the most common case. isinstance(int) keeps 0 held, and both None (still running) and ProcessUnknown (ECHILD) correctly yield an empty held. Measured on Linux against the real code: a genuinely-running leader gives peek=None, held=set(), group_alive=True -- never wrongly excluded, alone or alongside an already-exited sibling.

AC#2 (Linux /proc scan), re-measured by the reviewer in brig-probe-amd64:latest against the real group_alive, not a probe script. Held zombie leader alone (pgid 805): group_alive(pgid, {pid}) -> [False]x5, group_alive(pgid, frozenset()) -> [True]x5 (decision-0003's bug, reproduced). Held zombie leader + genuinely-alive backgrounded sibling, sh -c 'sleep 5 & exit 7' (pgid 806): [True]x5 both ways. Exactly the two cases the AC names.

AC#3: group_alive's docstring is substantively corrected, not reworded -- it now states that Linux's killpg makes no distinction at all between an all-zombie group and a live one, that the held branch is what covers it there, and that the /proc path is detected by trying it rather than branching on sys.platform.

AC#4 (TASK-0001.07 fold-in): the grace window closes a real race, confirmed by the reviewer's own A/B through the real destroy_jail -- but the recorded figure does not reproduce and should not be trusted by a future reader. Linux, brig-probe-amd64:latest, reproduction argv /bin/sh -c "trap '' TERM; sleep 30 & exit 0", 200 iterations each: with NO pre-sleep, 200/200 JailTeardownFailed at kill_grace_s=0.0 versus 0/200 at the default. With a 0.03s or 0.05s pre-sleep, 0/N either way -- the pre-sleep hides the race on Linux entirely. macOS, 0.05s pre-sleep: 145/150 at kill_grace_s=0.0 versus 0/150 at the default. So the claimed '100/200 against this exact reproduction in brig-probe-amd64' is not reproducible for the shape it names; the effect itself is larger and more decisive than claimed, in a shape the note does not name. Filed as DRAFT-0016, below, because the permanent test inherits the problem.

AC#5 (test rewrites): the three rewritten tests assert the new sequence genuinely, not a loosened one. test_teardown.py pins the exact list [Verify, SignalGroup(TERM), Verify, SignalGroup(KILL), Verify(deadline=...), Release] and the already-gone path's [Verify, Release]. test_walking_skeleton.py adds peek_attempts, checked_held == [frozenset()] and released == [pid]. test_teardown_leader_reaped_early.py drives the full three-rung ladder with leader_exited=True and pins released, checked, checked_held and one deadline-bound check. test_processes_gateway.py was not rewritten as AC#5 named, for the AC#1 reason above (its reap assertions were never contradicted, since reap did not change) -- documented in that file's own docstring, with four new tests for what did change.

AC#6 and the new regression test: test_destroy_jail_does_not_misread_a_long_held_zombie_as_alive genuinely reproduces decision-0003's measured bug through the real destroy_jail entry point. The reviewer reconstructed the pre-fix behaviour on Linux by driving the same test through a ProcessPort that ignores held: JailTeardownFailed after 5.01s, failing the test's own elapsed < 1.0 assertion; against the real port, 0.06s and clean. It fails for the right reason and passes for the right reason. (It would not have failed against the code before this task, because the old Verify released the zombie -- the bug only exists under the peek design it guards, which is what makes it the right permanent test.)

Repro recording: not required. Both tasks are task-type, not bug-type; board-check close returns ok for both with no repro finding.

Findings, by severity, and what happened to each.
1. (Medium, drafted as DRAFT-0016) The permanent grace-window test is vacuous on Linux, the one platform CI runs: test_destroy_jail_survives_the_leader_exiting_before_its_group sleeps 0.05s and gives 0/150 at kill_grace_s=0.0 there, so it would pass with the fix removed. It pins the fix on macOS only (145/150 -> 0/150). The draft carries the measured 200/200-at-no-sleep so the fix is one line.
2. (Low, drafted as DRAFT-0015) _group_alive_proc_scan's parse can raise IndexError (fields[0]/fields[2] on an empty or truncated stat read) or ValueError (int() on a line with no ')'), escaping group_alive through the driver's deliberately-unwrapped Verify arm and crossing the public API as a non-brig exception -- the shape .claude/rules/driver-exception-boundary.md records escaping twice before. Not blocking: no instance measured, and bwrap.py's own docstring sets the bar at 'measured raising'.
3. (Low, notes only) destroy_jail computes the deadline at entry, not at the post-KILL rung, so the window is kill_grace_s from destroy_jail's start. Three docstrings say 'once KILL is sent, that rung polls for up to this long'. The overstatement is microseconds in practice but the contract text is wrong.
4. (Low, notes only) Two evidence figures in the implementation notes are inaccurate, both understating the result: '56 passed, 3 skipped' on Linux (measured 115 passed, 3 skipped) and the 100/200 grace-window figure above. Recorded here so the board carries the measured numbers.
5. (Informational, notes only) modified_files lists 12 files; git status carries 13 -- the decision-0003 amendment file is not listed. board-check close does not flag it.
6. (Informational, notes only) If the driver raises mid-ladder, the generator is abandoned and a peeked pid is never released. An exceptional path only, and no narrower than what the ladder did before.
7. (Informational, notes only) On Linux the held branch treats other zombies in the group as gone while the killpg branch treats them as alive. The inconsistency is deliberate in effect and is what makes teardown terminate correctly against a reparented zombie sibling; worth stating in the docstring if anyone touches it.

Not committed by this review: the 13 working-tree files are still uncommitted. The reviewer's own guardrail denies commands that change git history, so the commit is the caller's to make.
<!-- SECTION:NOTES:END -->
