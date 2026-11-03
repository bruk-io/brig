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
   every place where the host keeps sockets the jail could dial (decision-0008 item 5). **Argv is
   one of the enumerated shared media**, as the old law said: anything on a command line brig
   starts is visible in `ps` to every user who can see the process, for as long as it runs, and is
   counted, never excused because the exposure is the host's rather than the jail's. brig's own
   argv carries only paths (the supervisor's script, channel endpoints) and the embedder's
   command; the environment and stdio travel by pipe and fd, never argv. *Held by*
   `tests/e2e/test_channel_exclusivity_battery.py`, `tests/e2e/test_cross_jail_channel_battery.py`
   and the socket case in `tests/e2e/test_report_battery.py`; the argv count has no test yet, and
   the claim's grade does not yet include it.
10. **Prove gates by planting violations.** A probe or test that observes a clean run proves
    nothing. Every enforcement claim has a battery that attempts the violation and a positive
    control that proves the probe works, and every bug fix lands its failing test first. *Held
    by* each battery above, and the pypeeker rule tests that plant each rule's violation.

## Domain

`src/brig/domain/` is pure: it imports nothing outside `domain` and does no I/O; host facts, time
and identity come in as data. What should happen next is always a value: a compile returns a
**plan** or a refusal, never a side effect taken while deciding.

`policy/` is what an embedder states. `paths.py`'s `FsPolicy` is intent, not a mechanism
(decision-0007): readable roots, writable roots, write denies inside them, and masks, each an
absolute path that names the same place in the jail as on the host, the more specific path
winning where two overlap. Its refusals say why a request cannot be compiled: `refusal` (a path
not absolute, a mask hiding a root or a path brig needs, a root absent on the host, an entry
reached through a symbolic link inside a writable root), `cwd_refusal` (a working directory in
no root), `stdio_refusal` (a stdio path inside a writable root, through a link, or with another
name) and `interpreter_refusal` (a policy that does not mount the supervisor's interpreter).
`env.py`'s `EnvPolicy` is the environment's allow-list and `scrub_env` its filter; `stdio.py`'s
`Stdio` says where the command's fd 0, 1 and 2 come from. Mappings are `frozendict`, sequences
tuples (decision-0001 rule 8).

`jail_types/bwrap.py` is bwrap's slice: `compile_run` makes the plan, `compile_mounts` turns the
policy into one ordered tuple of mounts, from which `compile_supervisor_launch`'s argv,
`writable_shared_paths` and `ceilings` are all read. `channels.py` reserves each declared channel
in the jail's channel directory before the jail starts (decision-0002). `claims.py` and
`grades.py` hold the claims a compile states and `grade`, the one function that grades them
from evidence. A jail's runtime report is the ceiling its compile states per claim (`fs_write`,
`fs_read`, `network`, `env`, `channel_exclusivity`; `BEST_EFFORT` where the host could undo a
mount), and an e2e battery holds each ceiling to what it measures (decision-0008).

Where the domain and the world alternate, the exchange is a value too. `effects.py` names the
closed set a generator may yield: start the supervised command, await the supervisor's report,
signal a process group, verify it, release a pid. `operations.py` (create, start, destroy) and
`teardown.py` are generators of them, each **step** performed by a driver outside this layer and
its result sent back in. The teardown ladder verifies, sends TERM, verifies, sends KILL, then
polls until gone or a deadline passes; every verify only peeks the leader, and the last step
releases its pid (decision-0003).

Not yet built: `facts.py`, `records.py`, `identity.py`, `egress.py`, and the Seatbelt jail type.

## Infra

`src/brig/infra/` imports nothing from brig: every function takes and returns plain data, and
a value that means "unknown" is infra's own sentinel, translated at presentation's edge.

- `processes.py`: spawning a process as the leader of its own group (and session, where the
  interpreter allows), with a complete fd allow-list; signalling its group; peeking at a pid's
  exit without releasing it, and releasing it; asking whether the group is alive, at once or
  until a deadline.
- `files.py`: what is at a policy path on the host, the chain of links a lookup passes through,
  and a file's link count.
- `state_dir.py`: brig's state directory (`BRIG_HOME`, else `~/.brig`) and its empty read-only
  directory.
- `placeholders.py`: the directories made on the host for bwrap to mount over at absent paths,
  recorded per jail and removed once no live jail mounts over them (TASK-0027).
- `sockets.py`: the channel directory's creation and removal, finding and holding the jail's PID
  namespace, the verified connect that says a channel is ready (decision-0005), and signalling
  the jail's PID 1.
- `supervisor/`: the jail's PID 1 (decision-0002). `wire.py` and `program.py` assemble
  (`assemble.py`) into one stdlib-only file that refuses an interpreter older than 3.15;
  `link.py` is the host's end, starting it and reading its events. The supervised command is its
  child, under the same uid, so the supervisor makes itself non-dumpable before the command
  exists, and the bwrap compile drops every capability (`--cap-drop ALL`): the command can
  neither reopen the supervisor's fds through `/proc/1` nor ptrace it, so the exit code the host
  reports is the one `waitpid(2)` gave (decision-0006).

Not yet built: `tether.py`, `sandbox_exec.py`, `log.py` and the `proxy/` package.

## Presentation

`src/brig/presentation/` is the only layer that knows both of the others, and the only one that
raises. `ports.py` states what a driver needs from infra as `Protocol`s, so a test runs a driver
against a fake of the same shape, and holds the readiness outcomes an embedder matches on. A
port speaks domain's values or its own, never infra's: `jail.py`'s real wiring translates
infra's sentinels on the way in. `driver.py` performs a generator's effects through the ports,
for every jail type.

Each jail type's own presentation is its slice (decision-0007 item 5): `drivers/bwrap.py`
refuses and compiles the policy, writes the supervisor script, starts the jail through the
driver, holds its PID namespace for readiness, and exports `create_bwrap_jail`. What every jail
type shares is beside it: `jail.py` (the `Jail`, brig's state directory, and the real ports'
wiring), `api.py` (reserving channels, readiness, waiting, interrupting the command with
`SIGINT` through its supervisor, teardown) and `report.py` (a report as text). `errors.py` names
every exception an embedder can see, one per failure, so an embedder handles brig's own types
and never infra's. `src/brig/__init__.py` re-exports exactly this layer's surface and the
domain's plain data, nothing from infra.

Not yet built: `drivers/seatbelt.py` and `proxy_main.py`.
