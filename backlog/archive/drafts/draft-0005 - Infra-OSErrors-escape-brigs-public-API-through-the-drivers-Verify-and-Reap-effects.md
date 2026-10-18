---
id: DRAFT-0005
title: >-
  Infra OSErrors escape brig's public API through the driver's Verify and Reap
  effects
status: Draft
assignee: []
created_date: '2026-10-17 22:02'
updated_date: '2026-10-18 02:21'
labels:
  - brig
  - teardown
dependencies: []
parent_task_id: TASK-0001
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

TASK-0001.03's second adversarial review pass measured two infra exceptions escaping brig's
public API untranslated. `presentation/errors.py` states the opposite contract in its own module
docstring: "presentation/drivers/bwrap.py is the only module that calls infra, so it is the only
one that catches an infra exception and raises one of these in its place -- an embedder handles
brig's own types without ever needing infra's." The driver only honours that for `Spawn` (wrapped
in `JailSpawnFailed`); its `Reap`, `SignalGroup` and `Verify` cases wrap nothing.

Both were measured on macOS through the public API (`run_jail` then `destroy_jail`), on a jail
whose leader exited 0 while a member of its process group lived on -- the exact shape verified
teardown exists to catch:

1. `ChildProcessError` from `infra/processes.py`'s `reap` (`os.waitpid(pid, 0)`), raised at the
   ladder's post-KILL `Reap` rung when `run_jail` had already collected the leader. Reproduced
   6 times out of 6. Note the teardown itself succeeded -- `ps` confirmed no process of the group
   was left -- so brig killed the jail correctly and then reported a raw infra error instead of
   returning.
2. `PermissionError` from `infra/processes.py`'s `group_alive` (`os.killpg(pgid, 0)`), raised at a
   `Verify` effect. Observed once in the same scenario; `group_alive` catches only
   `ProcessLookupError`, so every other `OSError` `killpg` can raise (EPERM here) passes straight
   through. Not reproduced on demand, so its trigger is less pinned down than (1)'s.

Why this was not blocking TASK-0001.03: reaching the `Reap` rung needs the group still alive after
TERM *and* the leader's pid already collected, which needs a non-leader member outliving the
leader. A bwrap jail under `--unshare-all` (which implies `--unshare-pid`) plus
`--die-with-parent` is one host process, so producing the shape required bypassing
`create_bwrap_jail` and hand-spawning `/bin/sh -c '/bin/sleep 30 & exit 0'`. No acceptance
criterion of TASK-0001.03 fails and `just done` is green. But the ladder, the driver and
`errors.py`'s contract are all written generically, and decision-0001 rule 7 already rejected
"a bwrap jail has exactly one process" as a reason to implement a generic claim with a
leader-only mechanism -- the same reasoning applies to the error translation.

The fix was deliberately not attempted inside TASK-0001.03: what the ladder *should* do when the
leader is already collected but the group is still alive is a design choice, not a mechanical
translation, and it wants deciding rather than patching at the end of a review pass.

## Open questions

- [ ] What should the ladder do when the leader's pid is already collected but the group is still
      alive -- skip the `Reap` rung, or express "reap if still ours" as its own effect so the
      domain decides rather than the driver swallowing `ChildProcessError`?
- [ ] Does each uncaught infra exception get its own `presentation/errors.py` subclass (rule 13's
      "one subclass per failure"), or is there one `JailTeardownFailed`-style type that carries
      the infra cause via `__cause__`?
- [ ] Should `infra/processes.py`'s `group_alive` narrow what it answers `False` for, or is
      translating every non-`ProcessLookupError` `OSError` the driver's job alone (rule 1 says
      infra returns plain data, which argues for the driver)?
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Resolved by TASK-0001.06 and TASK-0001.08:

1. TASK-0001.06 gave the Reap rung's "leader already collected" case its own value (`ExitCodeUnknown`), discarded by `_reap_after_kill`, rather than skipping the rung or adding a new effect -- `reap`/`reap_deadline`/`reap_nowait` catch `ChildProcessError` and translate it, never raise it. (Open question 1, settled.)
2. One subclass per genuinely new failure stayed the answer (rule 13): `group_alive`/`signal_group`'s fix did not need a new `presentation/errors.py` type at all, because the chosen answer to question 3 (below) means nothing escapes the driver for either of them to translate. (Open question 2, settled -- no new type needed for this pair.)
3. TASK-0001.08 chose infra's own side: `group_alive` now catches `OSError` broadly (not just `ProcessLookupError`) and answers `False`; `signal_group` wraps its call the same way and answers nothing (its contract was already `None`). Rule 1's "infra returns plain data" argues for infra deciding this, not the driver -- the driver has no plain-data shape of its own to fall back to the way `group_alive`'s `bool` already does. (Open question 3, settled.)

Checked while closing TASK-0001.08's AC#2 ("no teardown rung can leak a raw OSError") for the *whole* rung, not just the `killpg` calls: the `Verify` rung's other infra call (`reap_nowait`) and the `Reap` rung's (`reap`, `reap_deadline`) all go through `os.waitpid`, which this review's own measured case (1) already fixed for `ChildProcessError`/ECHILD. `os.waitpid`'s only other POSIX errno is `EINVAL` (bad options), unreachable here since brig always passes `0` or `os.WNOHANG`; `EINTR` is retried internally by CPython since 3.5 (PEP 475), never surfaced. So `ChildProcessError` is the only `OSError` subtype these three can raise for a pid brig itself spawned, and the existing `except ChildProcessError` already covers it -- no further change needed in `infra/processes.py` or the driver for this draft's scope. Verified by code inspection (POSIX `waitpid(2)` contract, CPython's documented EINTR retry) rather than by forcing EINVAL/EINTR in a test, since neither is reachable through this codebase's own call shape to force.

All three open questions above are answered by committed work; this draft looks ready to archive or promote-and-close, but that call is left to whoever reviews TASK-0001.08 rather than made here.
<!-- SECTION:NOTES:END -->
