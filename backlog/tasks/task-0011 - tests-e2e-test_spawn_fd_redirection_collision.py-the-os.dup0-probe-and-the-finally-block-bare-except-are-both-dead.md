---
id: TASK-0011
title: >-
  tests/e2e/test_spawn_fd_redirection_collision.py: the os.dup(0) probe and the
  finally-block bare except are both dead
status: To Do
assignee: []
created_date: '2026-10-18 14:48'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found closing TASK-0008. TASK-0008 removed _fill_fd_holes_below but kept, and promoted in the docstring, the 'probe_fd = os.dup(0); os.close(probe_fd)' pair with the comment 'this process's lowest free fd -- proves no holes below it'. The probe discards its value and mutates nothing. POSIX already guarantees os.pipe() returns the lowest free fds, so the very next line 'request_read_fd, request_write_fd = os.pipe()' establishes the contiguity on its own; the probe proves nothing the code then uses. The module docstring's 'The allocation is deterministic without this test filling anything in: os.dup(0), immediately closed, always returns...' therefore credits determinism to a statement that does no work -- the same class of untrue claim TASK-0008 was filed to remove. TASK-0008's AC#2 named the probe as 'the real reason', so this is a finding against that criterion, not against the work. Separately, the finally block's 'try: os.close(fd) except OSError: pass' can no longer fire: every fd reaching it is either -1 (skipped) or open, since both early closes now set their variable to -1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The os.dup(0)/os.close probe is removed, or its comment and the module docstring say what it actually establishes
- [ ] #2 The module docstring credits the determinism to POSIX lowest-free-fd allocation by os.pipe() itself
- [ ] #3 The finally block closes each fd without a bare except OSError, or the except is justified by a path that can actually raise
<!-- AC:END -->
