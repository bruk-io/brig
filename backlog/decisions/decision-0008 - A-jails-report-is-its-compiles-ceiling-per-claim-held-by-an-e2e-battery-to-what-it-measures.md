---
id: decision-0008
title: >-
  A jail's report is its compile's ceiling per claim, held by an e2e battery to
  what it measures
date: '2026-11-03T03:56:00Z'
status: accepted
---
## Context

TASK-0021: an embedder showing its person how well a jail holds needs a grade per axis of
enforcement at runtime: what the command may write (`fs_write`), read (`fs_read`), reach on the
network (`network`) and see of the environment (`env`), beside `channel_exclusivity`. Until now
`Grade` and `Evidence` existed only inside e2e batteries, and one claim was stated in `src`. A
battery cannot run each time a jail starts, and a grade must never be stated before something
proves it (rule 11: honest grades).

## Decision

1. **The compile states a ceiling per claim** (`bwrap.ceilings`): the strongest grade the jail it
   compiled can have, decided from what it compiled, pure. The `Jail` carries it as `report`.
2. **A fourth grade, `BEST_EFFORT`**: it holds unless the host itself changes what the jail
   mounts. `fs_write` and `fs_read` are best-effort while a write deny or a mask is mounted inside
   a writable root: the mount is on the host's directory entry there, and the host replacing that
   entry (an editor saving by rename) detaches it in the jail.
3. **Each ceiling is held to evidence**: `tests/e2e/test_report_battery.py` plants each claim's
   violation against a real jail with a positive control beside it, grades it with `grade`, and
   asserts the jail's report is no stronger (`at_most`). It runs in `just done`, so a commit
   cannot ship a ceiling its battery does not back; a regression in a mechanism grades the claim
   lower there and fails the ceiling.
4. `channel_exclusivity` keeps its definition: any writable path shared with the host that is not
   a declared channel, a writable root included, makes it `VIOLATED`.

## Consequences

- An embedder reads `jail.report[FS_READ_CLAIM]` and so on, and shows the word.
- A new claim needs its ceiling and its battery in the same change.
- Which media a jail can dial read-only (the dialable-socket draft) is not graded by any of
  these; that draft decides whether `channel_exclusivity` counts them.
