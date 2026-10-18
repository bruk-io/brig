---
id: decision-0002
title: >-
  The supervisor, request channels, and the grading skeleton: the next slice's
  shape
date: '2026-10-18 02:27'
status: accepted
---
## Context

Decision-0001's step 4 schedules the filesystem policy, the environment, channels, the teardown
ladder in full, grades and their batteries, the log envelope, egress, then Seatbelt. It does not
separately schedule building the supervisor, even though its own layout names
`infra/supervisor/{wire,program,link}.py`. Tracing actual dependencies rather than the stated
order shows the supervisor is load-bearing for more of that list than its absence from the order
suggests:

- The log envelope's open question (on TASK-0001) ties the envelope's design to "the supervisor
  program['s] first log line." Egress's open question asks whether enforcement routes "through
  the supervisor to the proxy." Both name the supervisor as part of their own design, not brig-seed's.
- A real jail under `--unshare-all` implies `--unshare-pid`: something has to be PID 1 inside that
  namespace. Today nothing is; `infra.processes.spawn` starts the real command directly as a child
  of the embedder's own process, and the host tracks the resulting process *group* from outside the
  jail. That is exactly why TASK-0001.07/.08/.09 exist: zombie reparenting, PID reuse, and a
  process-group probe that can answer EPERM are all consequences of tracking a group from outside
  rather than owning it from inside. A supervisor that reaps everything inside the jail and reports
  one clean outcome would let the host track exactly one process instead of a group.
- The old brig (measured facts cited as "old SPEC decision-NNN" per decision-0001's own
  convention; source pointed to by the owner, not copied into this repository, and never named
  here) worked out a request-channel design over several rulings:
  - old SPEC decision-184/185/186: a channel is a reservation (`name`, `bound_path`, `endpoint`)
    against a per-jail channel directory, made before the process starts and passed to it via
    **argv, never env** (nothing that strips environment variables can lose it). Readiness is a
    **verified connect**, never path existence — decision-185 fixed a real confused-deputy hole
    where a co-tenant process symlinked a reserved socket path to something outside the jail, and
    a naive path-existence check reported it ready anyway.
  - old SPEC law 9 (nothing crosses the boundary anonymously) and law 4 (observation is read-only
    or it is not observation) tie channels directly to grading: declared channels plus enumerated
    shared media are a graded claim (`channel_exclusivity`), not a side detail.
  - "Control" (interrupt/kill) is a separate category in the old SPEC, delivered by mechanism-level
    means (signal to group, pipe-EOF) — this already matches brig-seed's existing teardown/
    `SignalGroup` design. It needs no new mechanism, only the hardening already in flight.
- No grading mechanism exists in brig-seed yet: no `claims.py`, no `grades.py`, no `grade()`
  function. This is central to why the rewrite exists at all (decision-0001's own framing: "grades
  are stated before anything proves them"). Old SPEC law 1 (honesty over strength) and law 10
  (prove gates by planting violations) state the discipline plainly, and brig-seed's own house
  rule 11 already commits to it.

## Decision

1. **Build the supervisor next**, ahead of channels, the teardown ladder in full, the log
   envelope, and egress — not ahead of everything: filesystem policy, environment scrubbing, and
   the grading skeleton (below) have no dependency on it and can proceed in parallel. Minimal
   first version: `infra/supervisor/wire.py` (newline-delimited JSON over a pipe: one exec
   request in, a stream of `started`/`exited`/`done` events out), `program.py` (forks the real
   command, reaps everything reparented to it as PID 1, reports `done` once nothing remains),
   `link.py` (the host's end, using the existing `infra.processes.spawn` to start it — stdlib
   only, assembled with `wire.py` into the one file dropped as PID 1, per rule 17). New domain
   effects (`StartSupervisedCommand`, `AwaitSupervisorDone`) replace most of today's direct
   `Spawn`/`Reap`/`Verify` shape for the normal path; `SignalGroup` stays, since the supervisor
   still needs telling to shut its child down on TERM/KILL.
2. **Request channels** get a contract shaped by the old SPEC's measured lessons, not reinvented
   from nothing: `domain/channels.py` (`Channel`, `Reservation` as plain frozen data — name,
   bound_path, endpoint), `infra/sockets.py` (the per-jail channel directory and the reservation
   itself), and a verified-connect readiness primitive behind `presentation/ports.py` — readiness
   is a connect that succeeds *and* is confirmed to be the process's own listener, never path
   existence, specifically so brig-seed does not reintroduce the confused-deputy hole old brig
   found and fixed.
3. **"Control" needs no new mechanism.** It is brig-seed's existing teardown/`SignalGroup` work,
   already in flight (TASK-0001.07/.08/.09). **"Shared media" is not a mechanism to build**; it is
   an enumeration obligation that feeds the grading skeleton in (4).
4. **Scaffold grading now**, independent of (1)-(3): `domain/claims.py` (`Claim`),
   `domain/grades.py` (a `Grade` enum and `grade(claims, evidence) -> Mapping[Claim, Grade]`,
   where a claim with no evidence grades `unenforced`, per rule 11's own text), and
   `presentation/report.py`. The two e2e batteries that already exist (TASK-0001.05's
   fd-inheritance and TIOCSTI ones) wire in as the first real claims once the skeleton exists;
   building it does not wait on the supervisor or channels.
5. **Revised order for decision-0001's step 4**: supervisor first; filesystem policy, environment
   scrubbing, and the grading skeleton in parallel with it; then channels, the teardown ladder in
   full (revisited against the supervisor's simplification), the log envelope, and egress — both
   of the latter two name the supervisor in their own open questions, so design them after, not
   before; Seatbelt can start as soon as the supervisor's wire *shape* (not full implementation) is
   settled, since `program.py`/`wire.py` are meant to be jail-type-agnostic.

## Consequences

- TASK-0001.07/.08/.09's hardening, in flight as this decision is written, is **not wasted** —
  the host still needs to robustly wait on one process either way — but its process-group-probing
  complexity should shrink once the supervisor lands. **This decision does not choose** whether to
  let that work finish as currently scoped against the pre-supervisor architecture, or pause it
  until the supervisor's shape is clearer: that is an area of concern left for the owner, not
  settled here.
- The log envelope's and egress's open questions on TASK-0001 are now answerable in terms of the
  supervisor's wire protocol rather than independently of it, and should be designed after (1)
  lands, not before.
- Channels' design borrows measured lessons from old brig (the confused-deputy fix; argv-not-env
  for the reservation) without copying its code, and without this repository ever naming the
  program that old SPEC came from.
- Grading's skeleton existing early means every later slice's battery has somewhere to report its
  claim from day one, rather than grading being bolted on at the very end the way the pre-rewrite
  brig did it — the thing this whole rewrite exists to fix.

