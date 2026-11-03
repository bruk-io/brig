---
id: TASK-0022
title: >-
  The jailed command can forge the supervisor's events and ptrace it: run_jail
  returns an exit code the command chose
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:22:00Z'
updated_date: '2026-11-03T02:44:00Z'
labels:
  - size-5
dependencies: []
type: bug
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, and reproduced independently at 739dd94 (Linux 6.18, bubblewrap 0.9.0; as root, and by the reviewer as uid 1000).

The supervised command is the direct child of the supervisor, which is PID 1 of the jail's PID namespace, under the same uid, and the jail mounts its own procfs (`--proc /proc`, decision-0004). So the command can reopen the supervisor's events pipe through `/proc/1/fd/<n>` whatever fds `program.py`'s spawn closed, and write a `done` of its own:

```
supervisor fds: {'0': 'socket:[20062]', '1': 'pipe:[20731]', '2': 'pipe:[20731]', '4': 'pipe:[20068]'}
wrote forged done via fd 4
run_jail -> 42 after 0.05s; real command finished yet: False
```

`run_jail` trusted the forged exit code while the real command was still running. The reviewer also measured, as uid 1000, `ptrace(PTRACE_ATTACH, 1)` succeeding and `/proc/1/mem` opening read-write: the command can take over brig's trusted PID 1 outright, not only its wire. Teardown still holds (killing the supervisor tears the namespace down), so nothing outlives `destroy_jail`; what breaks is everything the host believes the supervisor told it (old SPEC laws 6 and 8), and `program.py`'s own claim that the exit code is `waitpid`-authenticated.

The fd closes cannot fix this: a child with the same uid that can read `/proc` reaches its parent. Candidate fixes, for a decision first: run the command in a nested PID namespace (and its own procfs) so the supervisor is not its `/proc/1`; run it under another uid; make the supervisor non-dumpable (`PR_SET_DUMPABLE 0`, which makes `/proc/1/fd` and ptrace refuse a same-uid peer) and check what that leaves; or authenticate the events channel another way.

Reproduction (from the repository root, `uv run python <file>`):

```python
import sys, time, brig
INSIDE = (
    "import os, time\n"
    "for n in os.listdir('/proc/1/fd'):\n"
    "    if os.readlink(f'/proc/1/fd/{n}').startswith('pipe:'):\n"
    "        try:\n"
    "            fd = os.open(f'/proc/1/fd/{n}', os.O_WRONLY)\n"
    "            os.write(fd, b'{\"kind\": \"done\", \"exit_code\": 42}\\n'); os.close(fd)\n"
    "        except OSError: pass\n"
    "time.sleep(4)\n"
)
t = time.monotonic()
jail = brig.create_bwrap_jail((sys.executable, "-I", "-c", INSIDE))
print(brig.run_jail(jail, timeout_s=15), f"{time.monotonic() - t:.2f}s")  # 42 0.05s; the real command exits 0 after 4s
brig.destroy_jail(jail)
```
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision recorded on how the supervisor is kept out of the supervised command's reach (which fix, and what it leaves)
- [ ] #2 An e2e battery plants the forgery (a write onto the supervisor's events pipe through /proc/1/fd) and a ptrace attach on the supervisor, and fails if run_jail returns the forged exit code or the attach succeeds, with a positive control
- [ ] #3 program.py's docstring states what authenticates the exit code, and it is true
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal for the migration (bh-02's TASK-0176 waits on it).

Repro at 88c7f8238f9c, test files: tests/e2e/test_supervisor_isolation_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_supervisor_isolation_battery.py` exited 1

(18 earlier lines omitted)
```text
        """decision-0006 item 2: `--cap-drop ALL`, so even a jail brig's root caller starts holds
        no capability inside its namespaces."""
        exit_code, _ = _exit_code_of(_CAPABILITIES)
>       assert exit_code == 0, "the jailed command holds capabilities"
E       AssertionError: the jailed command holds capabilities
E       assert 1 == 0

tests/e2e/test_supervisor_isolation_battery.py:119: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_supervisor_isolation_battery.py::test_a_command_cannot_forge_the_supervisors_done
FAILED tests/e2e/test_supervisor_isolation_battery.py::test_the_command_holds_no_capability
2 failed, 1 passed in 0.58s
```
<!-- SECTION:NOTES:END -->
