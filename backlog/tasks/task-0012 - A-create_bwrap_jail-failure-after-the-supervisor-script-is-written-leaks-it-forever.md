---
id: TASK-0012
title: >-
  A create_bwrap_jail failure after the supervisor script is written leaks it
  forever
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 16:16'
updated_date: '2026-10-18 17:25'
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
