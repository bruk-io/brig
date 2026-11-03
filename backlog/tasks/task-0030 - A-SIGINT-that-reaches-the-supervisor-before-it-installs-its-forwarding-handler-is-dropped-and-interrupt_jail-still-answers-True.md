---
id: TASK-0030
title: >-
  A SIGINT that reaches the supervisor before it installs its forwarding handler
  is dropped, and interrupt_jail still answers True
status: To Do
assignee: []
created_date: '2026-11-03T03:21:00Z'
updated_date: '2026-11-03T03:25:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0020 (e87d194). infra/supervisor/program.py _main starts the command (_start_child), closes _REQUEST_FD and emits 'started' (a pipe write that can block) before installing the SIGTERM/SIGINT handlers. As PID 1 of its PID namespace the supervisor ignores a signal it has no handler for, so an interrupt_jail in that window is sent (pidfd_send_signal succeeds, returns True) and lost. An embedder that interrupts only after its program said it is ready is in practice past the window, but nothing guarantees it, and an embedder that interrupts right after create gets True for nothing. Not measured. Fix: install the handlers (or block SIGINT/SIGTERM and unblock after) before starting the child, recording a signal that arrives before child_pid is known and forwarding it once it is.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A SIGINT or SIGTERM sent to the supervisor at any moment after the jail exists reaches the command, or interrupt_jail does not answer True
- [ ] #2 A test sends SIGINT before the supervisor reports started and shows it delivered
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at 3ade49ef46fd, test files: tests/e2e/test_interrupt_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_interrupt_battery.py -k as_soon_as` exited 1

(17 earlier lines omitted)
```text
>           assert delivered, "the jail's command was running, yet nothing was signalled"
E           AssertionError: the jail's command was running, yet nothing was signalled
E           assert False

tests/e2e/test_interrupt_battery.py:86: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_interrupt_battery.py::test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost
1 failed, 2 deselected in 3.18s
```
<!-- SECTION:NOTES:END -->
