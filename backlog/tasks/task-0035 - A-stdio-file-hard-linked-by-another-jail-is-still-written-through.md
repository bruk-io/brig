---
id: TASK-0035
title: A stdio file hard-linked by another jail is still written through
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T04:00:00Z'
updated_date: '2026-11-03T04:10:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0031 (8b42a6a). The worker's note says the no-link open covers a stdio path in a root another jail of the same embedder may write. It covers symbolic links only: that jail can replace out.txt with a hard link to a file the embedder owns on the same filesystem (protected_hardlinks allows it, same owner), and O_NOFOLLOW does not see it, so the next jail appends there. Not measured.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A stdio file opened for writing that is not a regular file with one link, owned by the embedder, is refused with an error saying what to do
- [x] #2 An e2e test hard-links a stdio path to an outside file from one jail and shows the next create does not write to it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at 0968f42e2705, test files: tests/e2e/test_cwd_stdio_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_cwd_stdio_battery.py -k hard_linked` exited 1

(25 earlier lines omitted)
```text
E             + beforeappended

tests/e2e/test_cwd_stdio_battery.py:177: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_cwd_stdio_battery.py::test_a_hard_linked_stdio_file_is_refused
1 failed, 7 deselected in 0.15s
```

Accepted 2026-11-03 under the owner's goal. The test commit e3bce5a's message names TASK-0033 and TASK-0034; it means TASK-0034 (the harmless link) and TASK-0035 (the hard link). The first repro recorded on TASK-0034 above was the hard-link case by mistake; the later one, the harmless-link case, is this task's.

Worker's report (Claude): fixed at bc4508f. An existing stdio file with st_nlink > 1 is refused before anything starts (infra.files.link_count; StdioHardLinked, raised as PolicyStdioHardLinked), and the open checks fstat's st_nlink again and refuses (a hard link made after the check fails the start). The repro above passes now, the other name's file untouched. uv run just done passes.

Review 2026-11-03 (reviewer): not closed. Full gate passes (recorded on TASK-0021). AC#2 met in substance and ticked: the e2e case hard-links from the host rather than from a jail, but the filesystem cannot tell the two apart, and the victim file stays untouched. AC#1 not met (measured): only st_nlink is checked. (a) A file owned by uid 65534, mode 0666, given as stdout: the jail ran and 'WROTE' was appended to it. The criterion requires the file to be owned by the embedder. (b) /dev/zero given as stdout was accepted and the jail exited 0. The criterion requires a regular file (/dev/null is the stated exception). To change: in link_count's lstat and in the post-open fstat in _open_through_no_link, also require S_ISREG and st_uid == os.geteuid(), with refusals and messages saying what to do, and add e2e cases for both. (low) The post-open fstat recheck (a hard link made after the up-front check) has no test.
<!-- SECTION:NOTES:END -->
