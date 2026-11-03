---
id: TASK-0027
title: Mountpoints for absent paths are left on the host after destroy_jail
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T03:53:00Z'
labels:
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. Measured: a writable project with read-only binds over two absent paths (`.envrc`, `.git/hooks`) and `/dev/null` bound over an absent `secret.env`. After `destroy_jail` the host project held a `.envrc` directory, `.git/` and `.git/hooks` directories and an empty `secret.env` file, none marked as brig's, none removed: bwrap creates a missing mountpoint on the writable source beneath it. A mask over an absent secret plants a file in the embedder's tree. Removing them safely needs to know which brig made and that no other jail still mounts over them (a mark, a record, a per-user lock or brig's verified process identity), which is bwrap knowledge an embedder should not have to carry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After destroy_jail, no mountpoint brig's compile caused to be created on the host remains, and none that existed before is removed
- [ ] #2 An e2e test plants absent write-denied and masked paths under a writable bind and shows the host tree is as it was after teardown, including while a second jail over the same tree still runs
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at aaa472ffcc53, test files: tests/e2e/test_placeholders_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_placeholders_battery.py` exited 1

(36 earlier lines omitted)
```text
E           AssertionError: assert ['.envrc', '.... 'secret.env'] == ['.git', 'kept.txt']
E             
E             At index 0 diff: '.envrc' != '.git'
E             Left contains 3 more items, first extra item: '.git/hooks'
E             Use -v to get more diff

tests/e2e/test_placeholders_battery.py:94: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_placeholders_battery.py::test_placeholders_outlive_no_jail_and_none_is_removed_under_another
1 failed in 0.17s
```

Accepted 2026-11-03. Worker's report (Claude): fixed at 9d9671e. infra/placeholders.py: hold() makes every directory missing on the way to each absent deny/mask target the compile mounts, records them with (st_dev, st_ino), and records which paths this jail holds (those it made, and any another jail's record says that jail made, so a placeholder still mounted by another jail is held too: found while building, when the second jail classed the first's placeholder as present and held nothing); attach() records the jail's bwrap by pid and start time; release(), under one per-user flock, drops this record and every dead one (alive while its bwrap, or before it starts its embedder, is the same process), removing each made directory no live record holds, still the same inode and empty, deepest first, and keeping a dead record's directories a live jail still holds for a later release. create_bwrap_jail holds before the supervisor starts and releases on a failed start (PlaceholdersFailed on an OSError); destroy_jail releases only once the jail is verified gone. tests/e2e/test_placeholders_battery.py (committed first; repro above: the tree kept .envrc, .git/hooks and secret.env): two jails over one tree; the first's teardown leaves the second's holds and the second still cannot create any held path; the second's teardown leaves the tree as it was (.git, there before, kept and empty). 5 runs in 5. uv run just done passes.
<!-- SECTION:NOTES:END -->
