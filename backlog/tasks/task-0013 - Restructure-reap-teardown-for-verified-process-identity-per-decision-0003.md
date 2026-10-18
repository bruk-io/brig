---
id: TASK-0013
title: 'Restructure reap/teardown for verified process identity, per decision-0003'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 19:06'
updated_date: '2026-10-18 19:11'
labels:
  - size-8
  - finish-moved
dependencies: []
references:
  - >-
    backlog/decisions/decision-0003 -
    Verified-process-identity-across-reap-and-teardown-peek-before-reap-no-pidfd-no-per-platform-split.md
modified_files:
  - src/brig/infra/processes.py
  - src/brig/domain/effects.py
  - src/brig/domain/teardown.py
  - src/brig/presentation/drivers/bwrap.py
  - src/brig/presentation/api.py
  - tests/unit/test_teardown.py
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
- [ ] #1 infra/processes.py's reap/reap_deadline/reap_nowait peek (WNOWAIT) rather than reap unconditionally; the real reap happens only once teardown's own ladder is done with that pid, via a new, explicit terminal release step (not hidden module state, not a change to effects.py's closed Effect union without updating every assert_never match site)
- [ ] #2 A new per-member group-liveness mechanism for Linux only: killpg there answers 'exists' identically for a zombie-only group and a genuinely-alive one, with no distinction -- a /proc-based enumeration excluding the known-held pid(s) is the named candidate, measured directly against real bwrap in brig-probe-amd64:latest for both the single-held-leader and the mixed (held leader + genuinely-alive sibling) cases. macOS's group_alive needs no change (confirmed: killpg's EPERM there already distinguishes 'entirely gone' from 'something still alive' correctly in both cases, verified empirically against the real function).
- [ ] #3 TASK-0001.08's group_alive docstring's 'the group is gone either way' reasoning is corrected to state the real, now-measured exception (a deliberately-held pid is not 'gone' on Linux, and must not read as gone there)
- [ ] #4 Landed with or after TASK-0001.07 (bounded grace period for multi-process groups), not independently -- TASK-0001.07 is specified against today's Verify/group_alive semantics and this task changes that premise
- [ ] #5 Every test decision-0003 named as contradicted (not just broken) by this change is rewritten, not patched: tests/unit/test_teardown.py's exact-effect-sequence assertions, tests/integration/test_teardown_leader_reaped_early.py's reaped/checked assertions, tests/integration/test_walking_skeleton.py's reaped == [] assertion, tests/e2e/test_processes_gateway.py's direct reap(pid) == ProcessUnknown() assertions
- [ ] #6 Full regression: just done green, and the existing walking-skeleton and teardown batteries pass for real against bwrap on Linux as well as macOS -- the platform divergence this decision found was invisible on macOS alone
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
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
finish-moved: created without acceptance criteria (a tool-sequencing artifact -- task create then a follow-up edit added them), then given its real ACs in the very next edit, drawn directly from decision-0003's own Consequences section. No scope added beyond what the decision already named; this is the task's first real shape, not a later narrowing or widening.

finish-moved: AC#2 narrowed from 'both platforms, mixed case unverified on either' to 'Linux only' after directly measuring the mixed case (held zombie leader + genuinely-alive backgrounded sibling) against the real macOS group_alive: it already answers True correctly, no redesign needed there. This is the decision-0003 amendment recorded the same day, carried into this task's own ACs rather than left stale.
<!-- SECTION:NOTES:END -->
