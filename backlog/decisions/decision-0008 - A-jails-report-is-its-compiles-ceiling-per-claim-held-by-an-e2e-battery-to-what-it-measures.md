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
   mounts. `fs_write` and `fs_read` are best-effort while any write deny or mask is mounted: the
   mount is on the host's directory entry, and the host replacing that entry (an editor saving by
   rename) can detach it in the jail, wherever it is. Measured both ways (TASK-0021's review: one
   kernel read the new file through a mask under a read-only root; this CI's kept the mask), so
   the grade allows for it everywhere.
3. **Each ceiling is held to evidence**: `tests/e2e/test_report_battery.py` plants each claim's
   violation against a real jail with a positive control beside it, grades it with `grade`, and
   asserts the jail's report is no stronger (`at_most`). It runs in `just done`, so a commit
   cannot ship a ceiling its battery does not back; a regression in a mechanism grades the claim
   lower there and fails the ceiling.
4. `channel_exclusivity` keeps its definition: any writable path shared with the host that is not
   a declared channel, a writable root included, makes it `VIOLATED`.
5. **`channel_exclusivity` counts what the jail can dial, not only what it can write** (the
   dialable-socket draft, decided here under the owner's goal for the migration; the owner may
   revisit it). A Unix socket accepts a connect through a read-only mount (measured: a jail under
   the default policy dialled a host listener in `/run`), so a jail that sees a place where the
   host keeps sockets shares that medium with the host. brig cannot list every socket on a host,
   so the ceiling uses the known places (`SOCKET_DIRECTORIES`: `/run`, `/var/run`, `/tmp`,
   `/var/tmp`, `/dev/shm`, plus the embedder's `XDG_RUNTIME_DIR`): a root that covers one, or lies
   inside one, without a mask over it, makes the claim `VIOLATED`. The default policy shows all of
   them, so it states the claim violated, which is what a jail under it is. A socket elsewhere
   than those places (inside a project, say) is not seen by this rule; the claim's description
   says what it covers.

## Consequences

- An embedder reads `jail.report[FS_READ_CLAIM]` and so on, and shows the word.
- A new claim needs its ceiling and its battery in the same change.
- An embedder that wants `channel_exclusivity` enforced reads no socket place: it names its
  readable roots, or masks those places.
