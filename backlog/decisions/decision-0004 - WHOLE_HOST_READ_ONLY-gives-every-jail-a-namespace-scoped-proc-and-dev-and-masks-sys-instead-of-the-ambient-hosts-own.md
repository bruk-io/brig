---
id: decision-0004
title: >-
  WHOLE_HOST_READ_ONLY gives every jail a namespace-scoped /proc and /dev, and
  masks /sys, instead of the ambient host's own
date: '2026-10-18 21:25'
status: accepted
---
## Context

Filed as DRAFT-0012, found while re-verifying TASK-0001.15/.16/.17's adversarial-review
fixes against real bwrap. `WHOLE_HOST_READ_ONLY` (`domain/policy/paths.py`) -- the default
`FsPolicy` every bwrap jail gets until an embedder names its own -- binds the whole host
root (`--ro-bind / /`) with no exclusions. That bind is recursive: it carries along
whatever is already mounted at `/proc` and `/sys` on the host, so a real bwrap jail under
this default policy gets the *ambient host's* `/proc`/`/sys`, not fresh ones scoped to the
jail's own PID namespace (bwrap does not auto-mount either unless told to). Measured
consequence: a jailed command can `ls /proc` and see every process on the host, by its
real host-side pid, not only its own jail's -- and, separately, every entry under `/sys`
(block devices, kernel modules, firmware). For the one relationship an earlier review
actually tested (the supervisor and its own direct child), the kernel's own ptrace-
permission model happened to deny the child reading the supervisor's `/proc/<pid>/fd/1`
-- but nothing about `WHOLE_HOST_READ_ONLY` itself prevents a jailed command from
listing, and attempting to introspect, every *other* process on the host, under whatever
ptrace settings that one host happens to have.

Three open questions were filed, unresolved: should the default exclude `/proc`/`/sys`;
does giving the jail its own namespaced `/proc` fully close this or only reduce blast
radius; and is relying on a host's own `ptrace_scope` configuration acceptable as part of
brig's own threat model at all.

## Decision

Measured directly against real bwrap (`brig-probe-amd64:latest`) before writing this down,
all three questions settled by the same set of measurements:

```
Without --proc: jail's own /proc listing includes 1, 8, 9 -- real HOST pids, not the
                 jail's own namespace's.
With --proc /proc added: jail's own /proc listing includes exactly 1 -- itself, nothing
                 else. The jail's own basic command (`true`) still runs and exits 0
                 with --proc /proc --dev /dev both added.
/sys without exclusion: lists the host's real block/bus/class/dev/devices/firmware/
                 kernel/module entries.
/sys masked with --tmpfs /sys (added after the ro-bind, so it shadows the recursive
                 host mount): lists nothing.
```

- **Yes, exclude the ambient host `/proc`/`/sys`/`/dev` from the default policy.**
  `WHOLE_HOST_READ_ONLY`'s own stated purpose is "the thinnest policy that lets the
  supervisor's own file be reachable" -- none of these three ever needed to be the
  *host's real* versions for that purpose. Structural, added unconditionally in
  `compile_supervisor_launch`, the same way `state_dir`'s own bind already is -- never
  part of the caller's own `FsPolicy`, since an embedder narrowing or widening their own
  policy has no business accidentally re-exposing or hiding these.
- **`--proc /proc` fully closes the `/proc` vector, not merely reduces it.** The jail's
  own listing after the fix contains exactly its own namespace's processes --
  measured, not inferred. This resolves the second open question directly: it is a
  structural fix (namespace-scoped mount, by construction), not a mitigation riding on
  any particular host's configuration.
- **`--dev /dev` gives a minimal, functional device set** (null, zero, random, urandom
  and similar) rather than the host's own real `/dev` -- the same reasoning as `/proc`,
  confirmed not to break the walking skeleton's own basic command.
- **`/sys` is masked empty (`--tmpfs /sys`), not given a scoped equivalent.** Unlike
  procfs, sysfs has no meaningful per-PID-namespace scoping to offer instead -- it
  reflects real host hardware/kernel state regardless of which namespace reads it, so
  the only safe default is absent, not "fresh." An embedder whose own policy genuinely
  needs hardware introspection can add their own `/sys` bind back explicitly; the
  default should not assume they do.
- **The third open question (relying on a host's own `ptrace_scope`) becomes moot for
  this vector once the above lands.** The jail can no longer *see* other host
  processes at all, via `/proc` or otherwise, so there is nothing left for a
  `ptrace_scope` setting to gate. This does not resolve `ptrace_scope` reliance in
  general, anywhere else it might matter -- only for the specific exposure this
  decision closes.

## Consequences

- `domain/jail_types/bwrap.py`'s `compile_supervisor_launch` gains a new, unconditional
  set of flags (a new named constant, not folded into `_NAMESPACE_FLAGS`, which is
  about namespace/behavior flags, not virtual-filesystem hygiene) placed after
  `state_dir`'s own bind, before the namespace flags: `--proc /proc --dev /dev --tmpfs
  /sys`.
- `tests/unit/test_bwrap_compile.py`'s existing byte-exact assertion on
  `compile_supervisor_launch`'s output needs updating for the new flags -- not a
  regression, the proof that nothing else changed.
- A new real-bwrap test is needed proving the jail's own `/proc` listing no longer
  contains host pids, and that `/sys` is empty, alongside the existing walking-skeleton
  journey still passing unmodified (the basic command must still work with the new
  flags in place).
- An embedder whose own policy specifically needs `/sys` (or the ambient host's real
  `/dev`/`/proc`) has to add it back explicitly -- a narrower default than before, by
  design. Not expected to affect any existing test or documented use case: nothing in
  this project's own walking skeleton, batteries, or the supervisor's own mechanics
  reads `/proc`, `/sys`, or `/dev` as the *host's* real ones (the supervisor's own reap
  loop is a pure `os.waitpid(-1, 0)` syscall, not `/proc`-based).

