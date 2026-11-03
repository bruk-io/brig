---
id: TASK-0025
title: >-
  A symlink at a write deny's or mask's path protects its target, not the path,
  so the command can replace it
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T03:06:00Z'
updated_date: '2026-11-03T03:16:00Z'
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
- [x] #2 An e2e test plants a symlink at a deny path inside a writable root and shows the command can neither write through it nor replace it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal. Measured before any change (bubblewrap 0.9.0, as root): writable root W holding hooks -> real (a symlink), write deny W/hooks; the command unlinked W/hooks, made a directory there and wrote W/hooks/pre-commit, exit 0, and the host's W/hooks is now a real directory. Confirmed: the deny protects the link's target, not the path.

Repro at b3ca718d3b4c, test files: tests/e2e/test_fs_policy_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_fs_policy_battery.py -k through_a_link` exited 2

(9 earlier lines omitted)
```text
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/e2e/test_fs_policy_battery.py:50: in <module>
    from brig import (
E   ImportError: cannot import name 'PolicyPathThroughLink' from 'brig' (/home/user/brig/src/brig/__init__.py)
=========================== short test summary info ============================
ERROR tests/e2e/test_fs_policy_battery.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.24s
```

Repro at cf160a7af541, test files: tests/e2e/test_fs_policy_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_fs_policy_battery.py -k through_a_link` exited 1

(17 earlier lines omitted)
```text
>           with pytest.raises(brig.PolicyPathThroughLink) as refused:
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^
E           AttributeError: module 'brig' has no attribute 'PolicyPathThroughLink'

tests/e2e/test_fs_policy_battery.py:551: AttributeError
=========================== short test summary info ============================
FAILED tests/e2e/test_fs_policy_battery.py::test_a_deny_reached_through_a_link_inside_a_writable_root_is_refused
1 failed, 13 deselected in 0.12s
```

Worker's report (Claude, 2026-11-03). Fixed at 0dc45c0. infra.files.facts returns each policy path's kind and realpath; paths.refusal takes them (HostPath) and refuses with ThroughLink any entry (root, deny or mask) inside a writable root whose resolved path is not the root's resolved path plus the rest of the entry: a link between them. A link above the writable root (which the command cannot change) refuses nothing. Raised as PolicyPathThroughLink(path, root) before anything is created. Tests: the e2e repro above (now passing: create_bwrap_jail raises, the link is untouched), unit refusal cases for a link inside a root and a link above it. uv run just done passes (recorded on TASK-0024.02, same tree).
<!-- SECTION:NOTES:END -->
