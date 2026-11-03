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
   battery measures (decision-0008), and `ENFORCED` only where a kernel mechanism holds it, never
   because a list of places found nothing (decision-0008's 2026-11-03 note). *Held by*
   `tests/e2e/test_report_battery.py` (each claim's report against its measured grade),
   `tests/e2e/test_ceiling_host_change_battery.py` (each violation the host's help lets through,
   against a report that allows for it), `tests/unit/test_report_ceilings.py` and
   `tests/unit/test_grades.py`.
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
   gone. A `create_bwrap_jail` that fails once its supervisor has started tears it down the same
   way, through the one cleanup `destroy_jail` runs, and the embedder never gets a running jail
   it has no `Jail` for (TASK-0044); so is a supervisor whose start failed after its spawn, which
   the start hands back on its `JailSpawnFailed` (TASK-0046). In both, the placeholders are
   released only once teardown reads the group gone, and a group that survives, or a teardown
   that raises before it can verify the group gone, is `JailTeardownFailed`; the cleanup never
   replaces the error of the step that failed, and adds its own to it as a note (TASK-0046). The pumps that carry the jail's stdio end with it: `destroy_jail` drains and closes
   them, so a command that never reads its stdin, or floods its stdout, cannot hold the host past
   teardown (TASK-0042). *Held by* `tests/e2e/test_interrupt_battery.py`,
   `tests/e2e/test_supervisor_reaps_orphans.py`, `tests/e2e/test_stdio_pumps_battery.py`, the
   teardown integration tests and, for a failed create, `tests/integration/test_create_failure_*`
   and `tests/integration/test_create_error_edges*`; a battery that plants survivors from the host is not yet
   written.
8. **Events are evidence, never the boundary.** No security claim rests on an event having been
   emitted: the supervisor's `started`/`done` say what happened, and the grades rest on
   batteries. *Held by* the report battery grading from measured evidence only.
9. **Nothing crosses the boundary anonymously.** `channel_exclusivity` grades whether the declared
   channels are the only shared media: every writable path the jail shares with the host, and
   every host path where a socket the jail could dial might sit (decision-0008 item 5 and its
   2026-11-03 note): a visible place where hosts keep sockets violates it, and any other root
   leaves it best-effort, since no list of places finds every socket. **Stdio is one of the
   enumerated shared media** (TASK-0042): what crosses it is only the bytes the embedder sends in
   and the command writes out, because the command's fd 0, 1 and 2 are always pipes the host
   pumps to and from the embedder's files or its own streams. Handed an fd on a host inode, a
   jail could reopen it through `/proc/self/fd/N` with whatever mode the file's permissions allow
   its uid (truncate a stdin file, read an append-only log); reopening a pipe reaches only the
   pipe. **Argv is
   one of the enumerated shared media**, as the old law said: anything on a command line brig
   starts is visible in `ps` to every user who can see the process, for as long as it runs, and is
   counted, never excused because the exposure is the host's rather than the jail's. brig's own
   argv carries only paths (the supervisor's script, channel endpoints) and the embedder's
   command; the environment and stdio travel by pipe, never argv. *Held by*
   `tests/e2e/test_channel_exclusivity_battery.py`, `tests/e2e/test_cross_jail_channel_battery.py`,
   the socket case in `tests/e2e/test_report_battery.py` and the socket outside every listed
   place in `tests/e2e/test_ceiling_host_change_battery.py`, and for stdio
   `tests/e2e/test_stdio_reopen_battery.py`; the argv count has no test yet, and
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
`Stdio` says where the command's fd 0, 1 and 2 are pumped from and to; the command itself always
gets pipes. Mappings are `frozendict`, sequences
tuples (decision-0001 rule 8).

`jail_types/bwrap.py` is bwrap's slice: `compile_run` makes the plan, `compile_mounts` turns the
policy into one ordered tuple of mounts, from which `compile_supervisor_launch`'s argv,
`writable_shared_paths` and `ceilings` are all read. A deny or a mask is a mount on the entry it
names, and a mount moves with its parent, so among the mounts are the pins (TASK-0001.31, old SPEC
decision-168): each directory strictly between a writable root and a deny, a mask or a readable
root nested in it (TASK-0001.33: an embedder's own code kept read-only inside a project), where the
jail shows it writable and it is no entry of the policy, is bound writable over itself before what
it leads to. A mount point refuses `rename(2)` inside the jail's mount namespace (`EBUSY`,
measured), so the command cannot move `W/a` away, taking the deny at `W/a/b/f` with it, and make
its own `W/a/b/f` for the host to read. Which of `pin_candidates` are directories is a host fact
presentation looks up; the directories brig makes for an absent deny or mask (its placeholders)
are made before the jail starts, so they are pinned too. What the pins cover is a rename from
inside the jail of a directory that was there when it started; what they do not is a directory
the host itself creates, removes or renames on the way while the jail runs. The cost: a rename
between a pinned directory and the rest of its root crosses a mount and fails with `EXDEV`. `channels.py` reserves each declared channel
in the jail's channel directory before the jail starts (decision-0002). `claims.py` and
`grades.py` hold the claims a compile states and `grade`, the one function that grades them
from evidence. A jail's runtime report is the ceiling its compile states per claim (`fs_write`,
`fs_read`, `network`, `env`, `channel_exclusivity`), and an e2e battery holds each ceiling to what
it measures (decision-0008). A ceiling is `ENFORCED` only where a kernel mechanism holds the claim,
never because a list of places found nothing (decision-0008's 2026-11-03 note); `BEST_EFFORT` holds
unless the host itself changes what the jail sees. `fs_write` is read from the compiled mounts: any
mount that is not writable whose nearest mount above is writable (a deny, a mask, a readable root
nested in a writable root) makes it `BEST_EFFORT`, since the host replacing that entry leaves the
jail writing there; the pins, writable over writable, do not count. `fs_read` is `BEST_EFFORT`
while a mask is mounted. `channel_exclusivity` is `VIOLATED` for a writable path shared beyond the
declared channels or a visible place where hosts keep sockets (`SOCKET_DIRECTORIES`), else
`BEST_EFFORT` while the jail sees any readable or writable root, where the host could keep a socket
it can dial. `network` follows the socket half of that rule only, since a dialable host socket can
carry the network: `VIOLATED` for a visible `SOCKET_DIRECTORIES` place, `BEST_EFFORT` while the
jail sees any root; a writable shared root alone carries files, not a route out, and does not
lower it.

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
  recorded per jail and removed once no live jail mounts over them (TASK-0027). A teardown sweeps
  every finished jail's directories together, deepest first, and one it cannot remove yet (not
  empty) stays in a record for a later sweep (TASK-0001.32).
- `sockets.py`: the channel directory's creation, the fd held on it, and its removal, finding
  and holding the jail's PID namespace, the verified connect that says a channel is ready
  (decision-0005), and signalling the jail's PID 1. A ready connect is handed back open, the one
  connection the check vouches for; a refusal, a failed connect and the one raise each close
  theirs (TASK-0001.34). The connect never follows a path the jail can change and never blocks
  (TASK-0045): the channel's name is opened beneath the held directory fd with
  `O_PATH | O_NOFOLLOW`, a symbolic link there is refused before any connect, anything else but
  a socket is not ready, and the socket is dialled through `/proc/self/fd/N` without blocking,
  so a full backlog is not ready at once.
- `supervisor/`: the jail's PID 1 (decision-0002). `wire.py` and `program.py` assemble
  (`assemble.py`) into one stdlib-only file that refuses an interpreter older than 3.15;
  `link.py` is the host's end, starting it and reading its events; a start that fails after
  the spawn hands back the spawned supervisor, unsignalled and unreaped, for the caller's verified
  teardown (TASK-0046). `pumps.py` carries the
  command's stdio (TASK-0042): the supervisor gets a pipe as each of fd 0, 1 and 2, and one
  thread per jail pumps each to or from the embedder's file or its own fd, never blocking on the
  jail's end; closing the supervisor (when `run_jail` sees `done`, and in `destroy_jail`) stops
  feeding stdin and pumps what the command wrote until end of file, for at most a bounded drain.
  A pump blocked on the embedder's own stream (a pipe nobody reads) is left behind, not waited
  for. The supervised command is its
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
type shares is beside it: `jail.py` (the `Jail`, brig's state directory, the real ports'
wiring, and `dismantle`: the verified kill ladder for a process that exists, then removing the
script, the channel directory and the fds, and releasing the placeholders only on a group read
gone, the one cleanup `destroy_jail` and a failed create both run; it raises nothing, and hands
back what its ladder or the supervisor's close raised, a raising ladder reading as a group not
verified gone, for its caller to attach to what it raises, TASK-0046), `api.py` (reserving channels, readiness, waiting, interrupting the command with
`SIGINT` through its supervisor, teardown) and `report.py` (a report as text).

An embedder talks to a channel only over the connection readiness verified. `await_channel_ready`
returns `ChannelReady(connection)`, the verified socket still open, and the embedder owns it and
closes it; it never dials the reservation's `bound_path` itself. The jail can write its channel
directory, so once readiness has passed it can replace its socket with a symbolic link to any
socket the embedder's user can reach on the host, and a plain connect follows the link
(TASK-0001.34). Readiness is a property of one connection (decision-0005 item 1): a second
connection is a second `await_channel_ready`. Only the attempt that reads ready leaves a socket
open. Readiness itself never dials as the embedder what the jail planted, and never outlasts its
deadline (law 7): `create_bwrap_jail` opens an fd on the channel directory as soon as it is
made and holds it on the `Jail` until `destroy_jail` closes it, each attempt opens the
reservation's name beneath that fd through no link, refuses a link there as `PEER_OUTSIDE_JAIL`
without connecting, and connects without blocking, so a jail that fills its own listen backlog
reads not ready until the deadline instead of holding the embedder (TASK-0045). *Held by*
`tests/e2e/test_channel_readiness_battery.py` (the swap after readiness),
`tests/e2e/test_channel_readiness_refusals.py` (every other outcome closes its socket),
`tests/e2e/test_channel_readiness_dial.py` (the deadline against a full backlog, and a planted
link never dialled) and `tests/e2e/test_channel_readiness_beneath.py`. `errors.py` names
every exception an embedder can see, one per failure, so an embedder handles brig's own types
and never infra's: a host that refuses brig's own state directory, its empty directory or the
supervisor script before a jail starts is `StateDirectoryWriteFailed` (TASK-0046). `src/brig/__init__.py` re-exports exactly this layer's surface and the
domain's plain data, nothing from infra.

Not yet built: `drivers/seatbelt.py` and `proxy_main.py`.
