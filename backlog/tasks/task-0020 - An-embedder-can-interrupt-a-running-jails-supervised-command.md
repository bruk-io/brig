---
id: TASK-0020
title: An embedder can interrupt a running jail's supervised command
status: To Do
assignee:
  - '@claude'
created_date: '2026-10-31T11:00:00Z'
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
