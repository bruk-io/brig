---
id: DRAFT-0022
title: A stdio file hard-linked by another jail is still written through
status: Draft
assignee: []
created_date: '2026-11-03T04:00:00Z'
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
