---
id: decision-0003
title: >-
  Verified process identity across reap and teardown: peek before reap for
  pid reuse, with group-aliveness redesigned to match on both platforms
date: '2026-10-18 17:46'
status: accepted
---
## Context

TASK-0001.03's adversarial review flagged a POSIX-wide hazard: once a pid is reaped, nothing
stops the OS from reusing that exact number for an unrelated process before teardown's next
probe or signal. `Verify` would then read the new process as the jail's own, and `SignalGroup`
would signal it. TASK-0001.03 fixed the two concrete bugs this produced at the time (see
`src/brig/domain/teardown.py` and `src/brig/infra/processes.py` as of that task) but left the
underlying hazard open, filed as DRAFT-0003.

*Correction to this decision's own first draft:* that draft described the release point as
`run_jail`'s blocking reap. That was true of the walking skeleton only. Since decision-0002/
TASK-0001.15, the normal journey's `operations.start` yields `AwaitSupervisorDone`, which the
driver performs with no reap at all (`presentation/drivers/bwrap.py`'s `AwaitSupervisorDone`
arm; `tests/integration/test_walking_skeleton.py` asserts `processes.reaped == []` on that path).
`Reap` is yielded in exactly one place today -- teardown's post-`SignalKind.KILL` rung, always
with `deadline=None` (`domain/teardown.py`'s `_reap_after_kill`) -- so `reap_deadline` currently
has zero production callers. The one release point on today's normal journey is `Verify`'s own
`processes.reap_nowait(process.pid)`, run non-blocking ahead of `processes.group_alive(process.pgid)`
every time teardown checks (`presentation/drivers/bwrap.py`'s `Verify` arm). `Process.pid`/`.pgid`
now name the supervisor (decision-0002), not the real command directly -- the hazard is the same
shape, just at a different pid than this decision's own first draft assumed.

The review named two directions, neither attempted (out of the walking skeleton's own scope):

1. **pidfd** (Linux `pidfd_open`): a stable fd handle on a process that cannot be reused for a
   different one. Linux-only; needs a separate story for Seatbelt/macOS and any future jail type
   without it.
2. **Verify before reap**: observe a process's exit without releasing its pid's identity until
   teardown has had its say, rather than reaping unconditionally.

Direction 2 was assumed to need the same per-platform split as direction 1, since a plain POSIX
`wait`/`waitpid` call necessarily reaps (observes and releases in one step) -- there is no way to
peek at a zombie's exit status without consuming it using those calls alone.

## Decision

`os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)` returns a zombie child's exit status *without*
releasing its pid for reuse -- a second call without `WNOWAIT` then performs the real reap, and a
third call afterward raises `ChildProcessError` (`ECHILD`), confirming the pid was only released
at the second call. Measured identically on macOS and real Linux (`brig-probe-amd64:latest`) with
a plain fork/exit child -- this part of the mechanism genuinely needs no platform split:

```
macOS (this host):           Linux (brig-probe-amd64:latest):
  peek:   si_status=7           peek:   si_status=7
  reap:   si_status=7           reap:   si_status=7
  re-peek: ECHILD (gone)        re-peek: ECHILD (gone)
```

**That single-pid measurement was not the whole hazard, and a second measurement -- against the
real group probe, not a bare `waitid` -- changed this decision's own shape.** `group_alive`
(`infra/processes.py`) answers `GroupState.ALIVE`/`GONE` by `killpg(pgid, 0)`: `ProcessLookupError`
(ESRCH) or, measured on macOS (TASK-0001.08), `PermissionError` (EPERM) both mean "gone" there,
swallowed to `False` because "the group is, for every purpose this probe exists to answer, gone
either way" (the function's own docstring). Held a zombie leader deliberately (peeked, not reaped)
and called the *real* `brig.infra.processes.group_alive` against it, on both platforms:

```
Held zombie leader, nothing else in the group:
  macOS:  group_alive() -> False   (killpg raises EPERM, swallowed as today's docstring says)
  Linux:  group_alive() -> True    (killpg SUCCEEDS -- a zombie-only group still answers alive)
```

Sampled 20x over one second on Linux with the leader held: `True` every time, not a transient.
This is the opposite of "no per-platform split needed." Deliberately holding a pid for direction
2's own sake turns it into exactly the zombie `group_alive`'s own docstring already describes --
except Linux's `killpg` does not treat a zombie-only group as gone the way macOS's does. Chased
through `teardown()`'s ladder, holding the leader through to the final `Verify` makes Linux read
`ALIVE` where macOS reads `GONE`, so `destroy_jail` would raise `JailTeardownFailed` on every
normal teardown on Linux -- the one platform brig's own CI actually runs bwrap on.

Decision, revised from this decision's own first draft in light of that:

- **Direction 2, not pidfd -- for the single-pid identity question only.** `WNOWAIT` still closes
  the raw pid-reuse hazard identically on both platforms; nothing about the `group_alive` problem
  above changes that. pidfd is not closed outright, only *not pursued for this problem*: it offers
  two things `WNOWAIT` genuinely cannot (a pollable handle `infra/supervisor/link.py`'s own
  `select.select([events_fd], ...)` loop could wait on in the same call, and race-free signaling
  via `pidfd_send_signal`) and neither is needed here, but a future problem that specifically wants
  either should reconsider it rather than finding this decision closed the door. pidfd also would
  not have solved the `group_alive` problem below on its own either way -- there is no pidfd for a
  process *group*, and the exposure here is on `.pgid`, not `.pid`.
- **A portable "is anything other than the pid(s) I'm deliberately holding still alive" probe does
  not exist off the shelf, and this decision does not invent one.** `group_alive` cannot keep its
  current one-syscall shape once something it is asked about is being held on purpose: it needs to
  tell "the pid I know I'm holding, zombie, expected" apart from "something else in this group,
  genuinely alive, unexpected" -- `killpg`'s single ESRCH/EPERM/success answer cannot make that
  distinction, on either platform, once a held pid is itself a group member. The honest shape of
  the fix: a per-member liveness check that excludes the specific pid(s) teardown is deliberately
  holding, which on Linux has no single portable syscall (candidate: enumerate `/proc/<pid>/stat`
  for every process reporting this `pgid`, skip the known-held one, answer alive if anything else
  remains) and on macOS needs its own re-verification, not an assumption that today's EPERM-swallow
  behavior still answers correctly once *some* member is held and *another* is genuinely alive at
  the same time (measured here only for a single-process group; the mixed case was not measured).
  This redesign is real, additional scope for whoever implements this decision -- not solved here.
- **Sequenced against TASK-0001.07, not independent of it.** TASK-0001.07 ("give the kill ladder's
  post-KILL verify a bounded grace period for multi-process groups") is specified against today's
  `Verify`/`group_alive` semantics. Changing what "alive" means for a group containing a
  deliberately-held pid changes the premise TASK-0001.07 is written against -- land one with the
  other in mind, not as two independent changes to the same function.
- **Still not a jail-type concern.** Whatever the per-member liveness redesign ends up being, it
  belongs in `infra/processes.py` (plain data in, plain data out, rule 1) -- nothing about *which*
  pid is held or *why* is a fact any `domain/jail_types/*` module needs to carry. This part of the
  original reasoning holds: no jail type needs its own identity-tracking logic, and Seatbelt
  inherits whatever `infra/processes.py` ends up doing with no extra work of its own -- though,
  per the measurement above, "inherits it for free" no longer means "inherits something already
  proven to work the same way everywhere"; it means "inherits whatever cross-platform liveness
  probe this decision's implementation task still has to design."

## Consequences

- A new implementation task is needed, materially larger than this decision's own first draft
  estimated. In scope: `reap`/`reap_deadline`/`reap_nowait`'s peek-vs-release split; a redesigned
  `group_alive` (or its replacement) that tolerates a deliberately-held pid on both platforms,
  with the Linux mechanism unverified as of this decision and the macOS mixed-case unverified too;
  a terminal release step somewhere once teardown's ladder is done with a pid (today's ladder has
  none -- a new effect, or a `destroy_jail`-level step, needs deciding); `effects.py`'s vocabulary
  (`ExitCodeUnknown`, `Reap`) for the new "peeked, not yet released" state its own docstrings don't
  describe today; and TASK-0001.08's `group_alive` docstring's own "gone either way" reasoning,
  which this decision's own measurement shows is not true once a hold is involved.
- Tests whose current assertions this contradicts, not merely breaks, and need rewriting rather
  than updating: `tests/unit/test_teardown.py`'s exact-effect-sequence assertions,
  `tests/integration/test_teardown_leader_reaped_early.py`'s `reaped`/`checked` assertions,
  `tests/integration/test_walking_skeleton.py`'s `reaped == []` assertion, and
  `tests/e2e/test_processes_gateway.py`'s direct `reap(pid) == ProcessUnknown()` assertions after a
  raw `os.waitpid` -- survive only if `reap` keeps releasing unconditionally, which this decision
  changes.
- pidfd stays available for reconsideration if a future need specifically wants a pollable handle
  or race-free single-pid signaling -- not closed outright, only not pursued for this problem.
- Full regression verification against the existing walking-skeleton and teardown batteries, on
  both macOS and real Linux+bwrap, is required before this implementation task can be considered
  done -- the platform divergence this decision measured was invisible on macOS alone.

