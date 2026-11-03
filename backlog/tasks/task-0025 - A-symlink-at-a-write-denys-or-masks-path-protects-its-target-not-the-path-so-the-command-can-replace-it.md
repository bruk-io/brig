---
id: TASK-0025
title: >-
  A symlink at a write deny's or mask's path protects its target, not the path,
  so the command can replace it
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T03:06:00Z'
updated_date: '2026-11-03T03:09:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0024.01 (c4ef292). infra/files.py kinds() follows links, and compile_mounts emits --ro-bind P P (or /dev/null / empty_dir onto P) for a deny or mask at P. A mount onto a symlink lands on the link's target; the link itself stays an ordinary entry in the writable root. A command (or an earlier jail sharing the root) that makes P a symlink, e.g. <root>/.git/hooks -> <root>/elsewhere, can then unlink P inside the jail and create a real directory there that it writes freely, defeating the deny; the source side also follows the link on the host, so a link to a path outside every root binds that target into the jail. Not measured by the reviewer (the review hook blocks scratch runs); measure against real bwrap first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A deny or mask whose path is a symlink is refused, or compiled so the path itself cannot be written, created or read, with the decision saying which
- [ ] #2 An e2e test plants a symlink at a deny path inside a writable root and shows the command can neither write through it nor replace it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal. Measured before any change (bubblewrap 0.9.0, as root): writable root W holding hooks -> real (a symlink), write deny W/hooks; the command unlinked W/hooks, made a directory there and wrote W/hooks/pre-commit, exit 0, and the host's W/hooks is now a real directory. Confirmed: the deny protects the link's target, not the path.
<!-- SECTION:NOTES:END -->
