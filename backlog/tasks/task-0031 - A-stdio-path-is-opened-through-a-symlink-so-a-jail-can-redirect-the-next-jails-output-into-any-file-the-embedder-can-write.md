---
id: TASK-0031
title: >-
  A stdio path is opened through a symlink, so a jail can redirect the next
  jail's output into any file the embedder can write
status: To Do
assignee: []
created_date: '2026-11-03T03:31:00Z'
updated_date: '2026-11-03T03:40:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0028 (d98bc84). infra/supervisor/link.py _open_stdio opens stdout/stderr with O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC in brig's own process: no O_NOFOLLOW, and the 0600 mode applies only when the file is created. When an embedder names a stdio path inside a root the jail can write (a log beside the work, reused across runs), the jailed command can replace it with a symlink to, say, ~/.bashrc, and the next create_bwrap_jail appends that jail's output there with the embedder's permissions; stdin likewise reads any file the embedder can. Not measured.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A stdio path whose last component is a symlink is refused (O_NOFOLLOW or equivalent), or a stdio path under a writable root is refused at create, with an error saying what to do
- [ ] #2 An e2e test plants the symlink from inside a jail and shows the next create does not write through it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at bb87cf97dfaf, test files: tests/e2e/test_cwd_stdio_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_cwd_stdio_battery.py -k writable_root` exited 1

(14 earlier lines omitted)
```text
            victim.write_text("before")
            (Path(root) / "out.txt").symlink_to(victim)
>           with pytest.raises(brig.PolicyStdioInWritableRoot) as refused:
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E           AttributeError: module 'brig' has no attribute 'PolicyStdioInWritableRoot'

tests/e2e/test_cwd_stdio_battery.py:86: AttributeError
=========================== short test summary info ============================
FAILED tests/e2e/test_cwd_stdio_battery.py::test_a_stdio_path_inside_a_writable_root_is_refused
1 failed, 4 deselected in 0.13s
```
<!-- SECTION:NOTES:END -->
