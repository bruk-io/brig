---
id: TASK-0024
title: >-
  A second jail type needs an intent-level policy and the per-type work in its
  own slice
status: To Do
assignee:
  - '@claude'
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T03:06:00Z'
labels:
  - size-8
dependencies: []
references:
  - >-
    backlog/decisions/decision-0007 -
    An-embedder-states-an-intent-level-FsPolicy-each-jail-type-compiles-it-bwrap-into-one-ordered-tuple-of-mounts.md
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. Two reviewers, reading separately, reached the same place.

- `FsPolicy` is ordered binds, "exactly what binds names, in the order given" (`domain/policy/paths.py`): bwrap's mechanism, not intent. brig cannot tell a root from a write deny from a read mask, so it cannot grade fs_write/fs_read against what the embedder meant (TASK-0021), and Seatbelt cannot honour a host-to-jail remap or a `/dev/null` bind. An embedder writing ordered binds today rewrites its policy when Seatbelt lands.
- The bwrap slice is inverted: `presentation/drivers/bwrap.py` is a generic effect interpreter with nothing of bwrap in it, while the bwrap-specific work sits in shared `api.py` (`_supervisors_for`, both reachability checks, `_namespace_fd_for`, `create_bwrap_jail`) and `Jail` carries a Linux PID-namespace fd. The launch argv is baked into a `LiveSupervisors` instance, never on `Plan` or `StartSupervisedCommand`, so the effect stream does not describe the jail (rule 10's dry run could not print it). Rule 3 says adding a type touches no other; Seatbelt would touch `api.py` and `__init__.py`.
- Bind order is an unwritten contract with three readers: `compile_supervisor_launch`, `writable_shared_paths` (rebuilds the order by hand) and `_check_channel_directory_reachable` (a synthetic bind standing in for it); both docstrings say a reordering breaks them silently.
- `ChannelReadinessPort.ready(path, jail_namespace_fd)` and decision-0002's PID-1 supervisor assume Linux PID namespaces, which macOS does not have.

Proposed shape, for the decision: an intent policy (writable roots; read roots or read-everything; write denies; read masks) that each jail type compiles, bwrap to a tuple of `Mount` values in the domain (the argv rendered from it, and writable paths and reachability computed over the same tuple) and Seatbelt to SBPL; the shared effect interpreter moved to `presentation/driver.py`; one `create_jail` with the per-type orchestration in that type's driver; the launch on the effect. Decide before the Seatbelt slice starts (TASK-0001 #4, which waits for a Mac run).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision recorded: the policy type an embedder writes, how each jail type compiles it, and where per-type orchestration lives
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal for the migration. Decided as decision-0007 (above). Built in two tasks below: the policy and mount compile (done, c4ef292), then the slice move.

Review (reviewer, 2026-11-03): not closed, AC1 not ticked. decision-0007 as committed (abc2aa6, HEAD) has empty Context, Decision and Consequences; its text exists only as an uncommitted change in the working tree, so the recorded decision is blank. Once committed, it still answers only part of what the task asks: it settles the embedder's policy and bwrap's compile, and where orchestration lives, but not how Seatbelt compiles the policy (no SBPL mapping, nor which intents it can and cannot honour, e.g. a mask as /dev/null), and not the Linux-only seams the description names: ChannelReadinessPort.ready's jail_namespace_fd, decision-0002's PID-1 supervisor on macOS, and putting the launch argv on the effect. Its reasoning holds for what it covers, apart from item 4's absent-entry rule (see TASK-0024.01's drafts). Also stays open while TASK-0024.01 and .02 are.
<!-- SECTION:NOTES:END -->
