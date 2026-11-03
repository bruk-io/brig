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

**Note, 2026-11-03 (TASK-0043): `ENFORCED` needs a kernel mechanism.** An architecture review
found three ceilings stated `ENFORCED` where only a list of places backed them, and a battery
(`tests/e2e/test_ceiling_host_change_battery.py`) now plants each. The rule: a ceiling reaches
`ENFORCED` only when a kernel mechanism holds the claim, never because a list of paths found
nothing. `BEST_EFFORT` (item 2) widens to match: it holds unless the host itself changes what the
jail sees, whether by replacing an entry a mount stands on or by keeping a listening socket under a
root. So:

- **`fs_write`** is computed from the compiled mounts, not the policy's roles: any mount that is
  not writable whose nearest mount above it is writable (a deny, a mask, a readable root nested in
  a writable one, brig's tmpfs over a state directory inside one) makes it `BEST_EFFORT`. The host
  renaming such an entry away moves the mount with it, and the jail writes into what the host
  makes there (measured on this kernel for a nested readable root). The pins are writable over
  writable and do not count. Item 2's "any mounted deny" becomes this.
- **`channel_exclusivity`** is `BEST_EFFORT` whenever the jail sees any host path a socket could
  sit in beyond its own channel directory: any readable or writable root, a file included (the
  host can rename a socket over it). The jail's channel directory, brig's own mounts (its state
  directory's tmpfs, the supervisor script, the empty directory and `/dev/null` a mask shows) and
  the jail's own `/proc` and `/dev` do not count. A list of places is not a mechanism: measured, a
  jail dialled a socket under a home directory that item 5's list does not name. Item 5's rule
  stays for `VIOLATED`: a visible `SOCKET_DIRECTORIES` entry, where hosts do keep sockets, or a
  writable shared root (item 4). Since every bwrap jail mounts its interpreter
  (`interpreter_refusal`), no bwrap jail is `ENFORCED` here today.
- **`network`** is capped by the socket half of `channel_exclusivity` only: the jail's own network
  namespace has no interface, but a host socket it can dial can carry the network (measured: a
  relay on a socket under a readable root carried the jail's bytes to a TCP listener). So it is
  `VIOLATED` where a `SOCKET_DIRECTORIES` place is visible (the default policy's is) and at most
  `BEST_EFFORT` while the jail sees any root. A writable shared root alone, which violates
  `channel_exclusivity` because it carries files, is not a route out and does not lower
  `network` (revised the same day: TASK-0043's first criterion tied `network` to the whole of
  `channel_exclusivity`, which graded every writable project `VIOLATED` for network).

What could earn the two back is a design draft ("A kernel mechanism to earn channel_exclusivity
and network back from best-effort"): this kernel's Landlock is ABI 7, whose socket scoping covers
abstract Unix sockets only, so the candidate is a supervisor-held listening fd per channel plus a
seccomp filter on `socket(AF_UNIX)`.

## Consequences

- An embedder reads `jail.report[FS_READ_CLAIM]` and so on, and shows the word.
- A new claim needs its ceiling and its battery in the same change.
- An embedder that wants `channel_exclusivity` no worse than `BEST_EFFORT` reads no socket place:
  it names its readable roots, or masks those places. `ENFORCED` waits for a kernel mechanism
  (the 2026-11-03 note).
