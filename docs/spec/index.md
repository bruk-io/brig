# SPEC

This is brig's normative spec (decision-0001 rule 18): the ten laws first, then one section
per layer. A behaviour change is a SPEC change first; new rulings belong to this board as
decisions, and the old SPEC's own rulings are cited as "old SPEC decision-NNN" — so a decision
number never means two different things. Terms below use the [glossary](../glossary.md)'s own
vocabulary rather than redefining it.

## The ten laws

The old SPEC's section 2, restated against this design (TASK-0036): each keeps its number and its
intent, names only what brig has, and says what holds it. These bind every jail type, driver and
future contribution; a change that violates one is a SPEC change first, code second.

1. **Honesty over strength.** A weak jail honestly reported beats a strong claim untested. Every
   claim a jail's compile states carries a grade in the jail's report, never stronger than an e2e
   battery measures (decision-0008). *Held by* `tests/e2e/test_report_battery.py` (each claim's
   report against its measured grade) and `tests/unit/test_grades.py`.
2. **Refuse, never downgrade.** A request brig cannot meet is refused with brig's own error before
   anything starts, never met partly: a policy it cannot compile, a stdio path a jail could
   redirect, an interpreter the policy does not mount. There is no fallback the caller did not
   write. *Held by* `tests/integration/test_policy_refusal.py`, the refusal cases in
   `tests/e2e/test_fs_policy_battery.py` and `tests/e2e/test_cwd_stdio_battery.py`.
3. **The policy is constant; only delivery varies.** An `FsPolicy` states intent (roots, denies,
   masks), and each jail type compiles the same value its own way (decision-0007); what varies per
   jail type is the grade each claim earns. *Held by* `tests/unit/test_fs_policy_compile.py` for
   bwrap; not yet tested across jail types, since Seatbelt is not built.
4. **Observation is read-only or it is not observation.** Anything that can inject into the jail is
   a channel, declared and reserved (`reserve_channels`), subject to policy. brig has no
   observation surface today; this binds any that is added. *Held by* nothing yet beyond the
   channel batteries (`tests/e2e/test_channel_*`).
5. **Authority never travels inbound as data.** What reaches a jail through a channel is only
   content; what the command does with it leaves through its declared channels, where the
   embedder's policy applies. brig carries no messages itself, so this binds embedders' channels
   and any relay brig adds (the egress proxy). *Held by* nothing in brig yet.
6. **Provenance is stamped by the deliverer.** What the host believes about a jail comes from code
   the command cannot reach: the supervisor's events are written by a PID 1 the command can
   neither reopen nor ptrace (decision-0006), never by the command's own claim. *Held by*
   `tests/e2e/test_supervisor_isolation_battery.py`.
7. **Control must not require cooperation.** Interrupt and teardown work when the command is
   spinning, wedged or hostile: `interrupt_jail` signals through the supervisor and loses nothing
   while the jail comes up; `destroy_jail` ends the jail's whole PID namespace and verifies it is
   gone. *Held by* `tests/e2e/test_interrupt_battery.py`, `tests/e2e/test_supervisor_reaps_orphans.py`
   and the teardown integration tests; a battery that plants survivors from the host is not yet
   written.
8. **Events are evidence, never the boundary.** No security claim rests on an event having been
   emitted: the supervisor's `started`/`done` say what happened, and the grades rest on
   batteries. *Held by* the report battery grading from measured evidence only.
9. **Nothing crosses the boundary anonymously.** `channel_exclusivity` grades whether the declared
   channels are the only shared media: every writable path the jail shares with the host, and
   every place where the host keeps sockets the jail could dial (decision-0008 item 5). Argv is a
   shared medium too: anything put in a command line is visible in `ps` to every user who can see
   the process, so brig puts no secret there (channel endpoints are paths, never secrets). *Held
   by* `tests/e2e/test_channel_exclusivity_battery.py`, `tests/e2e/test_cross_jail_channel_battery.py`
   and the socket case in `tests/e2e/test_report_battery.py`.
10. **Prove gates by planting violations.** A probe or test that observes a clean run proves
    nothing. Every enforcement claim has a battery that attempts the violation and a positive
    control that proves the probe works, and every bug fix lands its failing test first. *Held
    by* each battery above, and the pypeeker rule tests that plant each rule's violation.

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

`src/brig/domain/policy/` is what an embedder states. `paths.py`'s `FsPolicy` is intent, not a
mechanism (decision-0007): readable roots, writable roots, write denies inside them, and masks,
each an absolute path that names the same place in the jail as on the host, the more specific
path winning where two overlap. `refusal` says why a policy cannot be compiled: a path that is
not absolute, a mask hiding a root or a path brig needs, a root absent on the host, or an entry
reached through a symbolic link inside a writable root (a mount onto a link lands on its target,
and the command may replace the link). Each jail type compiles the
rest its own way: bwrap's `compile_mounts` into one ordered tuple of mounts, from which its argv
and its `channel_exclusivity` enumeration are both read. `env.py`'s `EnvPolicy` is the
environment's allow-list. `claims.py` and `grades.py` hold the claims a compile states and the
one function that grades them from evidence. A jail's runtime report is the ceiling its compile
states per claim (`fs_write`, `fs_read`, `network`, `env`, `channel_exclusivity`; `BEST_EFFORT`
where the host could undo a mount), and an e2e battery holds each ceiling to what it measures
(decision-0008).

Reserved, not yet built: `facts.py`, `records.py`, `identity.py`, `egress.py`, and a Seatbelt
jail type beside bwrap's.

## Infra

`src/brig/infra/` imports nothing from brig: every function here takes and returns plain data —
tuples, ints, stdlib types — and names no brig type, so nothing in this layer needs to know what
any of it means to a domain effect. `src/brig/infra/processes.py` is what exists today: spawning
a process as the leader of its own session and group, reaping it (with or without a deadline),
signalling its group, and checking whether any member of it is still alive.

`src/brig/infra/supervisor/` is the jail's PID 1 (decision-0002) and the host's end of its wire.
The supervised command is its child, under the same uid, so the supervisor makes itself
non-dumpable before the command exists, and the bwrap compile drops every capability
(`--cap-drop ALL`): the command can neither reopen the supervisor's fds through `/proc/1` nor
ptrace it, so the exit code the host reports is the one `waitpid(2)` gave (decision-0006).
`src/brig/infra/sockets.py` holds the channel directory's lifecycle and the readiness check.

Reserved, not yet built: `files.py`, `tether.py`, `sandbox_exec.py`, `log.py`, and the `proxy/`
package — decision-0001's layout for this directory, built out as later slices need them.

## Presentation

`src/brig/presentation/` is the only layer that knows both of the others, and the only one that
raises. `src/brig/presentation/ports.py` states what a driver needs from infra as a `Protocol`,
never the concrete infra module by name, so a driver can be run against a fake of the same shape
in a test. `src/brig/presentation/driver.py` is the one module that translates between domain's
effects and a port's plain-data calls, for every jail type — the one place that knows both, by
design (decision-0001 rule 1): an infra sentinel is translated into domain's own equivalent here,
and never crosses this boundary unchanged.

Each jail type's own presentation is its slice (decision-0007 item 5):
`src/brig/presentation/drivers/bwrap.py` refuses and compiles the policy, writes the supervisor
script, starts the jail through the driver and holds its PID namespace for readiness, and exports
`create_bwrap_jail`. What every jail type shares is beside it: `src/brig/presentation/jail.py`
(the `Jail`, brig's state directory, and the real ports' default wiring onto infra) and
`src/brig/presentation/api.py` (reserving channels, readiness, waiting, interrupting the command
with `SIGINT` through its supervisor, teardown).
`src/brig/__init__.py` re-exports exactly this layer's surface and the domain's plain data, nothing
from infra directly. `src/brig/presentation/errors.py` is where every raise an embedder can see is named: one
exception per failure, so an embedder handles brig's own types and never infra's.

Reserved, not yet built: `report.py`, a `drivers/seatbelt.py` beside `drivers/bwrap.py`, and
`proxy_main.py` — decision-0001's layout for this directory, for later slices.
