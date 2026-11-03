---
id: TASK-0034
title: A stdio path through a harmless link fails as a bare JailSpawnFailed
status: Done
assignee:
  - '@claude'
created_date: '2026-11-03T03:59:00Z'
updated_date: '2026-11-03T04:21:00Z'
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
- [x] #1 A stdio path whose lookup passes through a link is refused at create with an error that names the path and the link and says to give the resolved path, or is opened through a link no jail can write
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

Accepted 2026-11-03 under the owner's goal. The test commit e3bce5a's message names TASK-0033 and TASK-0034; it means TASK-0034 (the harmless link) and TASK-0035 (the hard link). The first repro recorded on TASK-0034 above was the hard-link case by mistake; the later one, the harmless-link case, is this task's.

Worker's report (Claude): fixed at bc4508f. stdio_refusal refuses a stdio path whose lookup passes through any link (its link_chain has more than one entry) with StdioThroughLink, raised as PolicyStdioThroughLink naming the path and saying to name what it leads to. The repro above passes now. uv run just done passes.

Review 2026-11-03 (reviewer): not closed. Full gate passes (recorded on TASK-0021). Measured: stdout=D/ln/out.txt with D/ln -> D/real is now refused before anything starts, with PolicyStdioThroughLink: "stdio path '.../ln/out.txt' goes through a symbolic link -- name the path it leads to (os.path.realpath) instead". AC#1 is not met as written: the error names the path and says what to do, but it does not name the link (D/ln). StdioThroughLink carries only the path, though link_chain already has the steps. To change: carry the first link in the chain on StdioThroughLink and PolicyStdioThroughLink, put it in the message, and assert it in test_a_stdio_path_through_any_link_is_refused_naming_it. Small, and no draft filed; it belongs to this task.

Repro at 24dac4f2a35c, test files: tests/e2e/test_cwd_stdio_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_cwd_stdio_battery.py -k any_link` exited 1

(25 earlier lines omitted)
```text
E            +  where None = getattr(PolicyStdioThroughLink("stdio path '/tmp/tmpr95tlvkk/logs/out.txt' goes through a symbolic link -- name the path it leads to (os.path.realpath) instead"), 'link', None)

tests/e2e/test_cwd_stdio_battery.py:160: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_cwd_stdio_battery.py::test_a_stdio_path_through_any_link_is_refused_naming_it
1 failed, 9 deselected in 0.09s
```

Worker, 2026-11-03, on the latest review, fixed at fe3f40d (see its message for each). TASK-0021: every mounted deny/mask caps fs_write/fs_read at BEST_EFFORT, with e2e cases for a host rename over a mask under a read-only root (this container keeps the mask, the reviewer's kernel did not: the grade allows for both) and a write at a deny. TASK-0034: PolicyStdioThroughLink names the link (infra.files.first_link). TASK-0035: an existing stdio path must be a regular file the embedder owns (PolicyStdioNotOwnFile; checked again once opened); e2e cases for another user's 0666 file and /dev/zero. TASK-0033: the gate failure came from the report battery writing os.environ; it now passes its environment as data; the rule's message names item writes. TASK-0036: law 9 counts argv as a shared medium again and says nothing tests it yet. uv run just done passes at fe3f40d.

Review 2026-11-03 (reviewer): closed. Full gate (uv run just done) exited 0 at fe3f40d plus board commits, recorded on TASK-0021; tree unchanged by it. AC#1 met: PolicyStdioThroughLink names the path and the first link (first_link), says to give the realpath, and the e2e case asserts .link.
<!-- SECTION:NOTES:END -->
