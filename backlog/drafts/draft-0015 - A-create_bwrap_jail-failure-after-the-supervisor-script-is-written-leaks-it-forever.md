---
id: DRAFT-0015
title: >-
  A create_bwrap_jail failure after the supervisor script is written leaks it
  forever
status: Draft
assignee: []
created_date: '2026-10-18 16:16'
updated_date: '2026-10-18 16:20'
labels:
  - brig
dependencies: []
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
- [ ] #1 A create_bwrap_jail call whose own run() raises before returning a Jail does not leave its freshly-written supervisor script behind
- [ ] #2 A test reproduces this exact shape (a failing supervisor spawn, e.g. via a fake/fixture that fails after the script write) and asserts the file is gone
- [ ] #3 A destroy_jail call that raises JailTeardownFailed (the kill ladder's last verify still found the group alive) does not leave the jail's own supervisor script behind either, or a decision record says why that shape stays accepted
- [ ] #4 A test reproduces the JailTeardownFailed shape and asserts on the chosen outcome
<!-- AC:END -->
