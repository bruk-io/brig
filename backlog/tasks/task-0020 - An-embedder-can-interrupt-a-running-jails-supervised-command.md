---
id: TASK-0020
title: An embedder can interrupt a running jail's supervised command
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T11:00:00Z'
updated_date: '2026-11-03T03:18:00Z'
labels:
  - size-2
dependencies: []
type: task
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder that runs a long-lived program in a jail (an interpreter it sends work to over a channel, say) needs to interrupt the work in flight without ending the program: SIGINT to the supervised command, which the program turns into its own cancellation and keeps running.

At a7e7f45 nothing public signals the supervised command. The supervisor (`infra/supervisor/program.py`) installs a forwarding handler for SIGTERM only, and the embedder holds the supervisor's `Process`, not the command's. Measured: `os.killpg` of the supervisor's group with SIGINT never reached a command that had a SIGINT handler installed and was waiting for it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The public API delivers SIGINT to a running jail's supervised command (the supervisor forwards it) and returns whether it was delivered, as data
- [ ] #2 A test shows the command receives SIGINT and keeps running, and that interrupting a jail whose command has finished is answered, not raised past the driver exception boundary
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal. Worker's report (Claude): built at e87d194. interrupt_jail(jail) -> bool (presentation/api.py) sends SIGINT to the jail's PID 1 through infra.sockets.signal_jail_pid1: the candidate is found under the jail's bwrap as jail_pid1_namespace finds it, a pidfd is opened, then the candidate is checked again (PPid still the bwrap, innermost pid still 1) and the signal goes through the pidfd, so a recycled pid is never signalled; a PID 1 that is a zombie or has no child left answers False (the command finished). The supervisor forwards SIGINT to its child with SIGTERM's handler. tests/e2e/test_interrupt_battery.py: a command with a SIGINT handler is interrupted, keeps running, exits 0 (8 runs in 8); interrupting a finished jail answers False. Seen failing with the old supervisor (SIGTERM only): the running case fails, then passes with the fix. Found while building: a finished jail's supervisor can still exist for a moment after run_jail returns, and signalling it then succeeds; the zombie/no-child check is what makes the answer honest. uv run just done passes at e87d194.
<!-- SECTION:NOTES:END -->
