---
id: TASK-0035
title: A stdio file hard-linked by another jail is still written through
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T04:00:00Z'
updated_date: '2026-11-03T04:04:00Z'
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
- [ ] #2 An e2e test hard-links a stdio path to an outside file from one jail and shows the next create does not write to it
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
<!-- SECTION:NOTES:END -->
