---
id: decision-0007
title: >-
  An embedder states an intent-level FsPolicy; each jail type compiles it, bwrap
  into one ordered tuple of mounts
date: '2026-11-03T03:01:00Z'
status: accepted
---
## Context

TASK-0024 (an architecture review, 2026-11-02). `FsPolicy` was ordered binds, "exactly what binds
names, in the order given": bwrap's mechanism, not intent. brig could not tell a root from a write
deny from a mask, so it could not grade what the embedder meant, and a second jail type (Seatbelt,
which takes a profile, not mounts) could not compile it. An embedder writing ordered binds would
rewrite its policy when Seatbelt lands. And the order was an unwritten contract with three readers:
the compile, `writable_shared_paths` (which rebuilt it by hand) and the channel-directory
reachability check (a synthetic bind standing in for it), each silently wrong if the order moved.

## Decision

1. **The policy is intent.** `FsPolicy(readable, writable, write_denies, masks)`: absolute paths that
   name the same place in the jail as on the host. No remapping: nothing needs it, and it was what
   made reachability a puzzle. The more specific path wins where two overlap. `WHOLE_HOST_READ_ONLY`
   is `FsPolicy(readable=("/",))`.
2. **The domain refuses what cannot compile** (`refusal`): a path that is not absolute and
   normalised; a mask that hides a root or a path brig needs (its state directory, a channel
   directory), since a mask is an empty read-only directory and nothing can mount beneath it; a
   root absent on the host, since a root is mounted from where it is (TASK-0026); and any entry
   reached through a symbolic link inside a writable root (TASK-0025), since a mount onto a link
   lands on the link's target while the link stays an entry the command may replace, so the entry
   would protect the target and not the path (measured: the command swapped a denied `hooks` link
   for a writable directory). Refused, not followed: an embedder that means the target names it.
   A link above every writable root refuses nothing, because nothing in the jail can change it.
   The check and the mount happen at different moments, so something else sharing the writable
   root could still swap a directory for a link between them; that window is noted on TASK-0025. These replace
   `StateDirectoryUnreachable` and `ChannelDirectoryUnreachable`: with every path at its real place
   and brig's state directory made before the jail starts, a mask is the one way left to hide one.
3. **Host facts cross in as data**: for every policy path, what is there (file, directory,
   absent) and where it resolves once links are followed, looked up by presentation through
   `infra/files.py` (`HostPath`).
4. **bwrap compiles to one ordered tuple of `Mount`s** (`compile_mounts`), shallowest path first and,
   at one path, root before deny before mask. A masked file mounts `/dev/null`; a masked directory,
   and a deny or mask at an absent path, mounts brig's empty read-only directory
   (`<state_dir>/empty`). An absent entry no writable root covers is dropped (nothing in the jail can
   create it, and bwrap could not make its mountpoint on a read-only mount); so is an entry inside a
   mask. Brig's own mounts follow (TASK-0019's state-directory mask). `render` makes the argv from
   the tuple and `writable_shared_paths` reads the same tuple; the `Jail` carries it.
5. **The per-type work moves into its slice** (a separate task under TASK-0024): the effect
   interpreter shared by every jail type moves to `presentation/driver.py`; bwrap's orchestration
   (`create_bwrap_jail`, the namespace scan) moves to `presentation/drivers/bwrap.py`; `api.py`
   keeps what every jail type shares (`run_jail`, `destroy_jail`, readiness, channels). Seatbelt then
   adds a domain module, a driver module and one re-export.
6. **Seatbelt compiles the same policy to a profile**, when its slice is built (TASK-0001
   criterion #4, waiting for a Mac run): readable roots to `allow file-read*`, writable roots to
   `allow file-read* file-write*`, write denies to `deny file-write*`, masks to
   `deny file-read* file-write*`, each a subpath or literal rule, the more specific rule last.
   Seatbelt matches paths rather than mounting, so a mask needs no `/dev/null` and an absent entry
   no mountpoint: every intent in `FsPolicy` maps to a rule. What this decision does not settle,
   left to that slice's own decision because only a Mac run can prove it: the readiness port's
   PID-namespace fd (`ChannelReadinessPort.ready`), decision-0002's PID-1 supervisor and
   decision-0006's non-dumpable protection on macOS, and whether the launch argv moves onto the
   effect so a dry run can print it.

## Consequences

- An embedder's policy is one value it can hand any jail type.
- Absent entries under a writable root leave the mountpoint bwrap made on the host (TASK-0015's
  draft, measured); cleaning them is that task's.
- `Bind`, `covering_ancestor_bind` and both reachability errors go, with the tests of their corners.
