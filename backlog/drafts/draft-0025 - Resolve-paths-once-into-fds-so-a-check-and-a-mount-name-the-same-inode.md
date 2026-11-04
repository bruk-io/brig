---
id: DRAFT-0025
title: Resolve paths once into fds so a check and a mount name the same inode
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T12:40:00Z'
labels:
  - brig
  - fs-policy
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: the rename and link bugs (TASK-0001.31, .33, .34, ThroughLink) share one cause: files.facts checks by path, placeholders.hold acts by path through parents, and bwrap resolves every mount again by path; the sweep is the same shape. Proposed: open each root and each entry beneath it with openat2(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS), take facts from fstat, make placeholders with mkdirat, pass fds to bwrap with --bind-fd/--ro-bind-fd (present in 0.9.0), and use --info-fd for the PID 1 instead of the /proc scan. Also: refuse a state directory inside or reached through any writable root (it holds the supervisor scripts and placeholder records). A design question for a decision record.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design review 2026-11-04: the draft overclaims; the jail-side renames are fixed by the pins (EBUSY) and stay, and the host-rename BEST_EFFORT stays. What fds close is the check-to-mount window on the source side. Recommended: walk one component at a time with O_PATH|O_NOFOLLOW and dir_fd (Python 3.15 has no os.openat2; one opener in infra/files.py replacing link._open_through_no_link and sockets.open_directory), facts from fstat, render writes --ro-bind-fd N (probed: works for files and directories, same inode inside), fds closed once the supervisor's first event arrives; --info-fd gives child-pid and pid-namespace, --block-fd holds the command until placeholders attach (ends TASK-0001.30's race). Amends decision-0007 items 3 and 4. Spike (size 2): does bwrap follow a link planted at a destination component inside an earlier writable bind; --info-fd/--block-fd under --as-pid-1; fd relocation with dozens of fds. Split: state-dir refusal (1), info-fd/block-fd (3), fd-sourced facts and mounts (5), placeholders by mkdirat and the sweep beneath a parent fd (3). Comes after DRAFT-0027's launch value.
<!-- SECTION:NOTES:END -->
