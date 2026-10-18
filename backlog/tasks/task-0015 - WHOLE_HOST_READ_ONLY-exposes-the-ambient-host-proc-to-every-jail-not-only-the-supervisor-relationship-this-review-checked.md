---
id: TASK-0015
title: >-
  WHOLE_HOST_READ_ONLY exposes the ambient host /proc to every jail, not only
  the supervisor relationship this review checked
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 07:18'
updated_date: '2026-10-18 21:27'
labels:
  - brig
  - size-3
dependencies: []
references:
  - >-
    backlog/decisions/decision-0004 -
    WHOLE_HOST_READ_ONLY-gives-every-jail-a-namespace-scoped-proc-and-dev-and-masks-sys-instead-of-the-ambient-hosts-own.md
modified_files:
  - src/brig/domain/jail_types/bwrap.py
  - tests/unit/test_bwrap_compile.py
  - tests/e2e/test_fs_policy_battery.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Description

`WHOLE_HOST_READ_ONLY` (`domain/policy/paths.py`) -- the default `FsPolicy` every
bwrap jail gets until an embedder names its own, documented as "the thinnest policy
that lets the supervisor's own file be reachable inside the jail at all" -- binds
the whole host root (`--ro-bind / /`) with no exclusions. That bind is recursive:
it carries along whatever is already mounted at `/proc` on the host, so a real
bwrap jail under this default policy gets the *ambient host's* `/proc`, not a fresh
one scoped to the jail's own PID namespace (bwrap does not auto-mount `/proc`
unless told to with `--proc`).

Measured consequence, found while verifying TASK-0001.15/.16/.17's adversarial-review
fixes against real bwrap (a privileged `ubuntu:24.04` container): a jailed command
can `os.listdir("/proc")` and see every process on the host, by its real host-side
pid, not only its own jail's. For the one relationship this review actually tested
(the supervisor and its own direct child), the kernel's own ptrace-permission model
denied the child reading the supervisor's `/proc/<pid>/fd/1` or `/proc/<pid>/environ`
-- this host's default Yama `ptrace_scope` only allows a process to introspect its
*descendants*, and the child is not an ancestor of its own parent. That measurement
does not generalize: nothing about `WHOLE_HOST_READ_ONLY` prevents a jailed command
from listing, and attempting to introspect, *every other* process on the host --
only the specific supervisor/child relationship was checked, under this one host's
ptrace settings, which decision-0001's own "knows nothing of the programs that embed
it" framing gives no reason to assume every deployment shares.

## Open questions

- [ ] Should `WHOLE_HOST_READ_ONLY` (or its eventual real per-embedder-policy
  successor) exclude `/proc` -- and `/sys`, likely the same question -- by default,
  the way the filesystem battery's own "mirror policy" already excludes virtual
  filesystems it has no use for (TASK-0001.16's own precedent, `tests/e2e/test_fs_policy_battery.py`)?
- [ ] If a jail's supervisor and real command ever need their own, intentionally
  namespaced `/proc` (so the jail's own view of `/proc` reflects only its own PID
  namespace, per `--proc`), does that fully close this, or only reduce its blast
  radius to processes that genuinely share the jail's own namespace?
- [ ] Is relying on the host's own Yama `ptrace_scope` an acceptable part of this
  library's threat model at all, given brig's own stated goal of grading what is
  actually enforced rather than what a particular host's default configuration
  happens to allow -- or does every claim resting on it need its own battery, the
  way TIOCSTI's closure already has one for `--new-session`?

## Context

Not a finding against TASK-0001.15/.16/.17's own six reported issues -- it is a
broader, pre-existing property of `WHOLE_HOST_READ_ONLY` itself (present before the
supervisor existed, for any jailed command able to read any host path), surfaced
while re-verifying one of those six fixes (the control-channel authentication hole,
DRAFT-0010) against real bwrap. See DRAFT-0010's own latest update for the specific,
narrower measurement (supervisor vs. its own direct child) that fix's own review
pass actually checked and closed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 domain/jail_types/bwrap.py's compile_supervisor_launch adds --proc /proc --dev /dev --tmpfs /sys unconditionally, after state_dir's own bind and before the namespace flags -- a new named constant, not folded into _NAMESPACE_FLAGS
- [ ] #2 A real-bwrap test proves a jail's own /proc listing contains only its own namespace's processes, not the host's (measured today: without the fix, 1/8/9 real host pids; with it, exactly 1 -- itself)
- [ ] #3 A real-bwrap test proves /sys is empty inside the jail
- [ ] #4 The existing walking-skeleton journey and every other real-bwrap battery still pass unmodified -- the new flags must not break the basic create/run/destroy path
- [ ] #5 tests/unit/test_bwrap_compile.py's byte-exact assertion on compile_supervisor_launch's output is updated for the new flags, proving nothing else in the compiled argv changed
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Measured already (decision-0004), reuse directly -- don't re-derive

- Without --proc: a real jail's /proc listing contains real host pids (1, 8, 9 measured).
- With --proc /proc added: listing contains exactly 1 (the jail's own process, correctly
  namespace-scoped) -- a structural fix, not a mitigation riding on ptrace_scope.
- --dev /dev confirmed not to break the walking skeleton's basic command (true, exit 0).
- --tmpfs /sys (added after the ro-bind, so it shadows the recursive host mount) lists
  nothing -- sysfs has no per-namespace scoping to offer instead, so masked-empty is the
  only safe default.

### Order of work

1. Add a new named constant in domain/jail_types/bwrap.py (e.g. `_VIRTUAL_FS_FLAGS =
   ("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/sys")`) -- document why it's
   separate from `_NAMESPACE_FLAGS` (virtual-filesystem hygiene, not namespace/behavior
   flags) and why it's unconditional, never part of the caller's own FsPolicy, same
   framing as `state_dir`'s own bind.
2. Insert it into `compile_supervisor_launch`'s returned argv: after the state_dir bind,
   before `_NAMESPACE_FLAGS`.
3. Update `tests/unit/test_bwrap_compile.py`'s byte-exact assertion for the new flags.
4. New real-bwrap tests in tests/e2e/test_fs_policy_battery.py: /proc listing contains
   only the jail's own namespace (reuse the exact measurement shape from decision-0004);
   /sys is empty.
5. Re-run the full existing e2e/integration suite against real bwrap to confirm nothing
   regresses -- the walking skeleton, fs-policy battery, supervisor batteries all still
   need to pass with these new flags unconditionally present.

### Proof

- just gates, just typecheck, just done green on macOS.
- Real Linux + bwrap (brig-probe-amd64:latest): new tests pass, full suite still green,
  not just the new/changed tests in isolation.

### Risks

- Argv ordering: --proc/--dev/--tmpfs must come after state_dir's own bind (so they
  aren't shadowed by it) and the policy's own binds, consistent with "later wins" bwrap
  semantics already established in this file's own docstrings -- verify against real
  bwrap, don't just reason about ordering.
- Confirm nothing in brig's own code (supervisor, driver, any test) reads the host's
  real /proc, /sys, or /dev from inside a jail -- decision-0004 states this is already
  confirmed true (the supervisor's own reap loop is a pure syscall), re-verify rather
  than re-assume now that the actual change is landing.
<!-- SECTION:PLAN:END -->
