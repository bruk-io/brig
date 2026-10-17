---
id: DRAFT-0005
title: >-
  Infra OSErrors escape brig's public API through the driver's Verify and Reap
  effects
status: Draft
assignee: []
created_date: '2026-10-17 22:02'
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
