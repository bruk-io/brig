---
id: TASK-0015
title: >-
  WHOLE_HOST_READ_ONLY exposes the ambient host /proc to every jail, not only
  the supervisor relationship this review checked
status: To Do
assignee: []
created_date: '2026-10-18 07:18'
labels:
  - brig
dependencies: []
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
