---
id: TASK-0034
title: A stdio path through a harmless link fails as a bare JailSpawnFailed
status: To Do
assignee: []
created_date: '2026-11-03T03:59:00Z'
updated_date: '2026-11-03T04:03:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0031 (8b42a6a). _open_through_no_link refuses a link anywhere on a stdio path, including one outside every writable root that no jail can change (a symlinked home, /var/run -> /run). Measured: stdout=D/ln/out.txt with D/ln -> D/real and the writable root elsewhere: create_bwrap_jail raises JailSpawnFailed('could not spawn jail process: ...') caused by NotADirectoryError, which names neither the path nor the link nor what to do.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A stdio path whose lookup passes through a link is refused at create with an error that names the path and the link and says to give the resolved path, or is opened through a link no jail can write
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at e3bce5a46cdb, test files: tests/e2e/test_cwd_stdio_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_cwd_stdio_battery.py -k hard_linked` exited 1

(25 earlier lines omitted)
```text
E             + beforeappended

tests/e2e/test_cwd_stdio_battery.py:177: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_cwd_stdio_battery.py::test_a_hard_linked_stdio_file_is_refused
1 failed, 7 deselected in 0.18s
```

Repro at 1b0fed4d8ca8, test files: tests/e2e/test_cwd_stdio_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_cwd_stdio_battery.py -k any_link` exited 1

(26 earlier lines omitted)
```text
E             + JailSpawnFailed

tests/e2e/test_cwd_stdio_battery.py:158: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_cwd_stdio_battery.py::test_a_stdio_path_through_any_link_is_refused_naming_it
1 failed, 7 deselected in 0.08s
```
<!-- SECTION:NOTES:END -->
