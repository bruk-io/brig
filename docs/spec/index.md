# SPEC

This is brig's normative spec (decision-0001 rule 18): the ten laws first, then one section
per layer. A behaviour change is a SPEC change first; new rulings belong to this board as
decisions, and the old SPEC's own rulings are cited as "old SPEC decision-NNN" — so a decision
number never means two different things. Terms below use the [glossary](../glossary.md)'s own
vocabulary rather than redefining it.

## The ten laws

Carried verbatim from the old SPEC's section 2, amendments folded in, per decision-0001 rule 18.
These bind every mechanism, driver and future contribution; a change that violates one is a SPEC
change first, code second.

1. **Honesty over strength.** A weak jail honestly reported beats a strong claim untested. Every
   axis of every report carries a grade; `detail` names the known gaps in prose. A mechanism that
   cannot deliver what the spec asks refuses (raises) — it never silently downgrades.
2. **Refuse, never downgrade.** Asking for a mechanism/stack/launcher by name gets that thing or
   an error. There is no fallback the caller did not write.
3. **The Spec is constant; only delivery varies.** Policy (denies, allows, limits, channels) is
   expressed identically whether it lands on a kernel jail or on nothing. What varies per stack is
   the grade each field earns.
4. **Observation is read-only or it is not observation.** Anything that can inject into the jail
   (a read-write attach, stdin) is a channel, declared in the Spec, subject to policy. Observation
   never appears in the enforcement report and never alters enforcement.
5. **Authority never travels inbound as data.** A message into a jail is only ever content.
   Everything a jailed process *does* with it exits back through declared channels where the
   embedder's policy applies. Corollary: a jail dialing or replaying its own inbound traffic gains
   nothing.
6. **Provenance is stamped by the deliverer.** Origin labels on inbound messages are written by
   trusted code at delivery time, never taken from the sender's claim.
7. **Control must not require cooperation.** Interrupt and kill are delivered by mechanism-level
   means that work when the jail is spinning, wedged, or hostile. Teardown reaches everything the
   jail contains (group, tree, namespace, container), never a single process, and is verified; its
   deliverability is graded per scope. (old SPEC decision-189: the "namespace" case is a supervised
   bwrap jail, whose instance is a pid namespace that ends with its PID 1, §8. *Amended, old SPEC
   decision-196:* each `Process` carries its `control` grade. *Amended, old SPEC decision-201:* the
   two scopes are the jail's (`Jail.destroy`, the report's `control` axis) and one process's
   (`Process.stop`, `Process.control`); each is graded no higher than a battery that plants
   survivors from the host proves, per jail type, §4.)
8. **Events are evidence, never the boundary.** Telemetry is best-effort by nature. No security
   claim may rest on an event having been emitted.
9. **Nothing crosses the boundary anonymously.** The exclusivity claim — "these declared channels
   and enumerated shared media are the only ways in or out" — is a reportable axis with a grade,
   like any other. **Argv is one of the enumerated shared media.** Anything a mechanism transits
   through the child's command line is visible in `ps` to every user who can see the process, for
   as long as it runs; §5's `EnvPolicy.set` is the first case brig ships. It is counted in the
   enumeration and covered by the `channel_exclusivity` grade, never excused from it because the
   exposure is the host's rather than the jail's. (old SPEC decision-093.) *Amended, old SPEC
   decision-202:* a jail type that can keep a value out of argv does: `oci` puts the environment
   in a file of mode 0600 that `docker create` reads and the runtime removes (§6), never in `-e`.
10. **Prove gates by planting violations.** A probe or test that observes a clean run proves
    nothing. Every enforcement claim has a probe that attempts the violation and a positive
    control that proves the probe mechanism itself works.

## Domain

`src/brig/domain/` is pure: it imports nothing outside `domain`, and does no I/O. What should
happen next is always a value, not an action taken in the deciding — a **plan**, or (once a jail
type needs to say no) a refusal, never a side effect reached for mid-decision. `src/brig/domain/plan.py`
holds the one producer of a plan today; `src/brig/domain/jail_types/bwrap.py` is bwrap's slice of
that decision, compiling a command into a plan with no caller yet for refusing one.

Where domain and the world must alternate — starting a process, waiting on it, signalling it,
checking it — the exchange is a value too: `src/brig/domain/effects.py` names the closed set a
generator may yield, and `src/brig/domain/operations.py` and `src/brig/domain/teardown.py` are
generators of them, each **step** performed by a driver outside this layer and handed back in. The
teardown ladder here is the verified kill sequence in its present form — verify, escalate, verify
again — not yet the fuller ladder (a grace period between signals, a final failure path)
decision-0001's order reserves for a later slice.

Reserved, not yet built: `facts.py`, `claims.py`, `grades.py`, `records.py`, `identity.py`,
`egress.py`, `policy/`, and a Seatbelt jail type beside bwrap's. These are decision-0001's layout
for this directory, filled in by decision-0001's order, step 4, not by this task.

## Infra

`src/brig/infra/` imports nothing from brig: every function here takes and returns plain data —
tuples, ints, stdlib types — and names no brig type, so nothing in this layer needs to know what
any of it means to a domain effect. `src/brig/infra/processes.py` is what exists today: spawning
a process as the leader of its own session and group, reaping it (with or without a deadline),
signalling its group, and checking whether any member of it is still alive.

Reserved, not yet built: `files.py`, `tether.py`, `sockets.py`, `sandbox_exec.py`, `log.py`, and
the `supervisor/` and `proxy/` packages — decision-0001's layout for this directory, built out as
later slices need them.

## Presentation

`src/brig/presentation/` is the only layer that knows both of the others, and the only one that
raises. `src/brig/presentation/ports.py` states what a driver needs from infra as a `Protocol`,
never the concrete infra module by name, so a driver can be run against a fake of the same shape
in a test. `src/brig/presentation/drivers/bwrap.py` is the one module that translates between
domain's effects and a port's plain-data calls for bwrap's jail type — the one place that knows
both, by design (decision-0001 rule 1): an infra sentinel is translated into domain's own
equivalent here, and never crosses this boundary unchanged.

`src/brig/presentation/api.py` wires a jail type's domain operations through its driver into the
real `brig.infra.processes` functions by default, and is brig's public entry point —
`src/brig/__init__.py` re-exports exactly this layer's surface, nothing from `domain` or `infra`
directly. `src/brig/presentation/errors.py` is where every raise an embedder can see is named: one
exception per failure, so an embedder handles brig's own types and never infra's.

Reserved, not yet built: `report.py`, a `drivers/seatbelt.py` beside `drivers/bwrap.py`, and
`proxy_main.py` — decision-0001's layout for this directory, for later slices.
