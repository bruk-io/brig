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
   write. *Held by* `tests/integration/test_policy_refusal.py`,
   `tests/integration/test_egress_policy_refusal.py`,
   `tests/integration/test_egress_create_refusal.py`, `tests/integration/test_egress_live_grants.py`
   (a grant to a running jail is checked as a created policy is), the refusal cases in
   `tests/e2e/test_fs_policy_battery.py` and `tests/e2e/test_cwd_stdio_battery.py`.
3. **The policy is constant; only delivery varies.** An `FsPolicy` states intent (roots, denies,
   masks), and each jail type compiles the same value its own way (decision-0007, decision-0010);
   what varies per jail type is the grade each claim earns. *Held by*
   `tests/unit/test_fs_policy_compile.py` for bwrap and `tests/unit/test_seatbelt_compile.py` for
   Seatbelt.
4. **Observation is read-only or it is not observation.** Anything that can inject into the jail is
   a channel, declared and reserved (`reserve_channels`), subject to policy. brig has no
   observation surface today; this binds any that is added. *Held by* nothing yet beyond the
   channel batteries (`tests/e2e/test_channel_*`).
5. **Authority never travels inbound as data.** What reaches a jail through a channel is only
   content; what the command does with it leaves through its declared channels, where the
   embedder's policy applies. brig carries no messages itself, so this binds embedders' channels
   and any relay brig adds (the egress proxy). *Held by* nothing in brig yet.
6. **Provenance is stamped by the deliverer.** What the host believes about a jail comes from code
   the command cannot reach: the supervisor's events are written by a root supervisor process the
   command can neither reopen nor ptrace (`PR_SET_DUMPABLE=0` and `--cap-drop ALL` in an unshared
   PID namespace on Linux, decision-0006; `ptrace(PT_DENY_ATTACH)` and no `/proc/<pid>/fd` on
   Darwin, decision-0010), never by the command's own claim. *Held by*
   `tests/e2e/test_supervisor_isolation_battery.py` and `tests/e2e/test_seatbelt_supervisor.py`
   (on Darwin the command can still signal its supervisor, which leaves the exit code unknown,
   never forged).
7. **Control must not require cooperation.** Interrupt and teardown work when the command is
   spinning, wedged or hostile: `interrupt_jail` signals through the supervisor and loses nothing
   while the jail comes up: the command receives it. What the command does with it is its own: a
   command that handles SIGINT can ignore it, and a Python command can swallow one that arrives
   during its own startup ("Exception ignored ... KeyboardInterrupt", TASK-0053); `destroy_jail` ends the jail's whole process group / PID namespace and verifies it is
   gone. A `create_bwrap_jail` or `create_seatbelt_jail` that fails once its supervisor has started tears it down the same
   way, through the one cleanup `destroy_jail` runs, and the embedder never gets a running jail
   it has no `Jail` for (TASK-0044); so is a supervisor whose start failed after its spawn, which
   the start hands back on its `JailSpawnFailed` (TASK-0046). In both, the placeholders are
   released only once teardown reads the group gone, and a group that survives, or a teardown
   that raises before it can verify the group gone, is `JailTeardownFailed`; the cleanup never
   replaces the error of the step that failed, and adds its own to it as a note (TASK-0046). The pumps that carry the jail's stdio end with it: `destroy_jail` drains and closes
   them, so a command that never reads its stdin, or floods its stdout, cannot hold the host past
   teardown (TASK-0042). A jail's egress proxy ends with it too: closing the supervisor (when
   `run_jail` sees `done`, in `destroy_jail`, and in a failed create's cleanup) tells the proxy
   to leave, kills its group if it has not, and reaps it, and a start that fails part way ends
   the proxy it began (TASK-0001.36), with its route full too: every connection it holds goes
   with it (TASK-0049). *Held by* `tests/e2e/test_interrupt_battery.py`,
   `tests/e2e/test_egress_route_battery.py`, `tests/e2e/test_egress_connection_caps.py`,
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
name) and `interpreter_refusal` (a policy that does not mount the supervisor's interpreter,
or a link on the way to it, as infra's `link_chain` follows the lookup the kernel makes: each
link before the `..` after it; a root that is itself one of those paths, such as a venv's
`python3` link, ends the walk, since bwrap binds what a root leads to at its own path;
TASK-0052).
`env.py`'s `EnvPolicy` is the environment's allow-list and `scrub_env` its filter; with an
egress policy, `proxy_environment(port)` is what the jail sets itself over it (`HTTP_PROXY`,
`HTTPS_PROXY` and `ALL_PROXY=socks5h://...` at the bridge on `127.0.0.1:<port>`, their
lower-case forms, and `NO_PROXY`/`no_proxy` empty; decision-0009 item 7), and
`proxy_variable_refusal` refuses an `EnvPolicy` naming any of `PROXY_VARIABLES` rather than
override it silently. A `Plan` carries those as `set_env`, laid over the scrubbed environment by
`operations.create`. `stdio.py`'s
`Stdio` says where the command's fd 0, 1 and 2 are pumped from and to; the command itself always
gets pipes. Mappings are `frozendict`, sequences
tuples (decision-0001 rule 8).

`egress.py` is where a jail may reach through its egress proxy (decision-0009 items 3 and 4,
TASK-0001.35). An `EgressPolicy(allow)` is a tuple of `Destination(host, port)`: the port always
named, no port wildcards, and the host one of three forms, an exact hostname, `*.suffix` (any name
under the suffix, never the suffix itself: "the site" and "its subdomains" are two grants), or an
exact IPv4 or IPv6 literal, bare. The empty `allow`, the default, is loopback and nothing else.
`egress_refusal` names the first entry that cannot be granted: an empty host, a port not from 1
to 65535, a `*` anywhere but a leading `*.`, CIDR notation, a host that is no valid hostname (an
ASCII name of 1-to-63-character labels, 253 characters at most, whose last label no resolver
would read as a number, so `127.1` and `0x7f000001` are refused, not looked up), or a bracketed
host. Names compare without case and with one trailing dot dropped; literals compare by value,
an IPv4-mapped IPv6 address as the IPv4 address it maps. `parse_authority` reads what an HTTP
`CONNECT` or an absolute URL names (`host:port`, `[v6]:port`, a URL's default port) into an
`Authority`, refusing, never trimming or guessing at, anything else with an
`AuthorityProblem`; a SOCKS5 request builds its `Authority` directly. `decide_egress` is the
whole decision, and it decides before anything is resolved: a literal request is allowed only by
a literal grant of that address and port, never by a name grant; a name request no exact or
suffix grant names with its port is `NotGranted` and never looked up, so the jail cannot use the
proxy's resolver as a way out; a granted one is `Resolve(name)`, and asked again with what it
resolved to, is `Allowed(grant, addresses)` only if every address is public or named, with the
same port, by an IP-literal grant. One address that is not public refuses the whole name
(`PrivateAddress`): loopback, link-local (169.254.169.254 and `fe80::/10` among them), RFC 1918,
unique-local (`fc00::/7`), unspecified, shared (`100.64.0.0/10`), reserved, multicast, site-local,
an IPv4-mapped or NAT64 address that carries one of these, every 6to4 and Teredo address, and
the host's own addresses, which come in as data. Public means the standard library's `ipaddress` calls it global, and
neither reserved nor multicast: wider than the ranges listed, so an address nobody thought of is
refused rather than reached. The proxy connects to `Allowed.addresses` and resolves nothing
again, so a name cannot rebind between the check and the connect. The old brig's filter allowed
by name alone (old SPEC decisions 133 and 134); the private-address rule is decision-0009's.

A running jail's grants change (decision-0009 item 5, TASK-0001.37): `egress_after(policy, kind,
destination)` is the one definition of an `EgressChangeKind.ALLOW` (append the destination
unless it is granted already, so which grant allows a request is kept) and a `REVOKE` (remove
every grant equal to it; a name under a `*.suffix` grant revokes nothing). The host's record and
the proxy's grants both apply it, so the two cannot disagree. `egress_reason` names the
`EgressReason` of a settled decision (`granted` for an allowed one, else the refusal:
`not-granted`, `unresolved`, `address-unparseable`, `private-address`,
`authority-unparseable`), and `egress_verdict` makes that `allowed` or `refused`, so the
proxy's decision lines and the embedder's values read one set of words. `egress_record.py` holds
what an embedder reads back: `EgressRecord(created, changes)`, each `EgressChange` a kind, a
destination and the time it was sent, with `granted_now` the grants its changes leave; and
`EgressDecision(seq, verdict, destination, reason, address, time, line)`, one per decision the
proxy made, `address` the private address a name resolved to when that refused it ('' otherwise),
so an embedder can offer the IP-literal grant that would open it. Times are aware UTC `datetime`s that enter as data.

`jail_types/bwrap.py` is bwrap's slice (its `ceilings` state `NETWORK_EGRESS_CLAIM` in place of
`NETWORK_CLAIM` for a jail with an egress policy, decision-0009 item 8, under the same socket
cap): `compile_run` makes the plan (with `egress_port`, the
proxy variables pointing at `EGRESS_BRIDGE_PORT`, 3128, on the jail's own loopback), `compile_mounts` turns the
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
in the jail's channel directory before the jail starts (decision-0002), and refuses, as a value, a
name that would escape it and an endpoint whose bytes and NUL do not fit AF_UNIX's `sun_path` (108
bytes on Linux, 104 on macOS; the platform's size enters as data), which `reserve_channels` raises
as `ChannelEndpointTooLong` (TASK-0001.38). `claims.py` and
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

`jail_types/seatbelt.py` is Seatbelt's slice on Darwin (decision-0010, TASK-0061): `compile_run`
makes the plan (with `egress_port`, setting the same proxy variables at `EGRESS_BRIDGE_PORT` on
loopback), and `compile_rules` turns the `FsPolicy`, `state_dir`, `supervisor_script`, the channel
directory and `egress_port` into one ordered tuple of rules: shallowest first, at both a path and
where it resolves when a link such as `/var -> /private/var` differs; `file-read-metadata` on each
root's ancestors; `allow file-read*` on readable roots (and `deny file-write*` on one nested in a
writable root); `allow file-read* file-write*` on writable roots; `deny file-write*` on write
denies and `deny file-read* file-write*` on masks; `deny file-write-unlink` pins on every writable
root but `/` and every directory between a writable root and a carve-out (old SPEC decisions 207
and 208); then brig's state directory masked, this jail's supervisor script readable, its
channel directory writable and its one place for Unix sockets, and with egress the bridge port.
`render_profile` renders them after a fixed header, each line of it measured: deny by default;
signals only within the jail's own sandbox; `setsid` and `setpgid` refused, so no process leaves
the group `destroy_jail` kills; one Mach service, the directory lookups; read on `/` itself, which
`dyld` needs; `/dev`'s null, zero and random devices and the process's own descriptors only. No
`(import "system.sb")`. Every rule is rendered through a Python 3.15 template string
(`string.templatelib.Template`, decision-0001 rule 16), escaping `\` and `"` and refusing a NUL
byte. `ceilings` states Seatbelt's grade ceilings per claim (decision-0010 item 4): `fs_write` is
`ENFORCED` when no non-writable subpath lies beneath a writable root and `BEST_EFFORT` when one
does (Seatbelt judges a path, so the host renaming or linking an entry on the way moves what lies
beneath it); `fs_read` is always `BEST_EFFORT` (the jail lists `/`, reads its roots' ancestors'
metadata and host processes' arguments, and looks up users and groups; and a mask follows a path,
not a file); `env` is `ENFORCED`; `channel_exclusivity` is `VIOLATED` when an undeclared writable
path is shared with the host and `ENFORCED` otherwise (Seatbelt refuses a dial of a host Unix
socket inside a readable root, a signal outside the jail, and every Mach service but the
directory lookups); `network` without `EgressPolicy` is `ENFORCED`, and with one
(`SEATBELT_NETWORK_EGRESS_CLAIM`) is `BEST_EFFORT` (SBPL's `localhost` matches every local
address, so a host service at the bridge port on a LAN address is reachable past the proxy, and
the command can listen at that port on the wildcard address).

Where the domain and the world alternate, the exchange is a value too. `effects.py` names the
closed set a generator may yield: start the supervised command, await the supervisor's report,
signal a process group, verify it, release a pid. `operations.py` (create, start, destroy) and
`teardown.py` are generators of them, each **step** performed by a driver outside this layer and
its result sent back in. The teardown ladder verifies, sends TERM, verifies, sends KILL, then
polls until gone or a deadline passes; every verify only peeks the leader, and the last step
releases its pid (decision-0003).

Not yet built: `facts.py`, `records.py`, and `identity.py`. (decision-0001's
layout put the egress decision at `domain/egress.py`; it is `policy/egress.py`, beside the other
policies an embedder states.)

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
- `placeholders.py`: the directories made on the host for bwrap to mount over or Seatbelt to pin
  at absent paths, recorded per jail (tagged with the `user.brig.placeholder` extended attribute
  and verified against process start time via `/proc/<pid>/stat` on Linux or
  `proc_pidinfo(PROC_PIDTBSDINFO)` on Darwin) and removed once no live jail holds them
  (TASK-0027, decision-0010). A teardown sweeps every finished jail's directories together,
  deepest first, and one it cannot remove yet (not empty) stays in a record for a later sweep
  (TASK-0001.32).
- `sockets.py`: the channel directory's creation, the fd held on it, and its removal, finding
  and holding the jail's PID namespace (or process-group identity fd on Darwin), the verified
  connect that says a channel is ready (decision-0005, decision-0010), and signalling the jail's
  PID 1. A ready connect is handed back open, the one connection the check vouches for; a refusal,
  a failed connect and the one raise each close theirs (TASK-0001.34). The connect never follows a
  path the jail can change and never blocks (TASK-0045): on Linux the channel's name is opened
  beneath the held directory fd with `O_PATH | O_NOFOLLOW` and dialled through `/proc/self/fd/N`,
  verified via `SO_PEERCRED` and `/proc/<pid>/ns/pid`; on Darwin the held directory fd's path is
  resolved via `fcntl(F_GETPATH)`, the entry is statted beneath `directory_fd` with
  `follow_symlinks=False` before and after connecting, and the peer is verified via
  `getsockopt(SOL_LOCAL, LOCAL_PEERTOKEN)` (`audit_token_t` with `euid`, `pid`, `pidversion`) plus
  `proc_pidinfo` (`PROC_PIDTBSDINFO` and `PROC_PIDUNIQIDENTIFIERINFO`) matching `p_idversion` and
  `pbi_pgid` against the jail's process group.
- `supervisor/` and `proxy/`, the jail's one route out (decision-0009 items 1 and 2,
  TASK-0001.36). With an egress policy, the supervisor's exec request names a bridge port: before
  the command starts it listens on `127.0.0.1:<port>` in the jail's own network namespace (and
  `[::1]` where the namespace has IPv6), and once the command runs it accepts on daemon threads.
  For each connection it makes a socketpair, sends one end to the egress proxy with
  `SCM_RIGHTS` over `wire.BRIDGE_FD` (5, its end of a `SOCK_SEQPACKET` pair on Linux, or
  `SOCK_STREAM` on Darwin where `AF_UNIX` `SOCK_SEQPACKET` is unsupported), and
  copies bytes between the other end and the connection, reading nothing of them. fd 5 is closed
  in the command like 3 and 4, and the supervisor stays non-dumpable, so the command reaches the
  proxy only through the port. No path is involved, so nothing in the jail's view names the
  proxy, and a program that ignores the proxy settings reaches nothing: the jail has no other
  interface and no resolver. `proxy/program.py` is the proxy, a host-side process per jail,
  standard library only and importing nothing of brig (the `brig-standalone-programs` gate,
  which holds the supervisor's two sources too). `proxy/assemble.py` builds its one file: the
  supervisor's version guard, then `domain/policy/egress.py`'s source, handed in as text by
  presentation and run as a module of its own, then the program, which takes that module as a
  value and reads it at one seam. So the proxy decides with exactly the domain's decision,
  without importing it. `proxy/launch.py` starts it from its stdin (`python -I -`, so no file
  names it), with a fixed environment, `/dev/null` as its output, its config as one JSON line
  on fd 3 (the grants and an optional resolver table; the write end is held for the jail's
  life, and closing it ends the proxy), and its end of the control pair on fd 4. The link
  starts it before the supervisor, and ends it when the supervisor is closed (`RunningProxy.end`:
  close the config pipe, wait briefly, kill its group, reap). The proxy sniffs each connection's
  first byte: SOCKS5 `CONNECT` (no authentication; IPv4, IPv6 or a name, `socks5h`), or HTTP
  `CONNECT host:port` and absolute-form `http://` (the request line rewritten to origin-form,
  the proxy and connection headers dropped, `Connection: close`). It asks `decide_egress` with
  no addresses first, resolves a name itself only on `Resolve` (through the host's resolver, or
  the embedder's table), asks again with the addresses and the host's own (`/proc/net/if_inet6`
  and the local table of `/proc/net/fib_trie` on Linux, or `getifaddrs` on Darwin, read per decision), and connects only to
  `Allowed.addresses`. A refusal is `403` with the body `brig: egress denied by policy:
  host:port`, or SOCKS reply `0x02`. A name that resolved to nothing is `502` or `0x04`, a
  failed connect `502` or `0x05`, and an unreadable request `400` or `0x01`. The SOCKS reply's
  bound address is always `0.0.0.0:0`, so the jail learns nothing of the host's.

  What a jail can hold of the host through its route is bounded (TASK-0049), by limits that are
  named constants in the programs. A test lowers them, and nothing raises them:
  - **The bridge** relays at most `wire.BRIDGE_CONNECTION_LIMIT` (256) connections at once,
    across its listeners, two threads each. One more is accepted and closed at once, with no
    answer, and never reaches the proxy.
  - **The proxy** serves at most `program.CONNECTION_LIMIT` (256) connections at once, one
    thread each and two once relaying. One more gets no thread: the proxy's own loop holds it
    until its first byte (at most as many again, each for at most the handshake deadline;
    past that it is closed unanswered). It answers `403` with the body `brig: egress refused:
    the jail holds as many connections as it may`, or a SOCKS5 method choice and reply `0x01`,
    and closes it. It makes no decision line, since it named no destination. The proxy's cap
    holds even against a supervisor that sent more than its own cap allows.
  - **A handshake** has `program.HANDSHAKE_DEADLINE_S` (30 s) in all, from the connection's
    arrival at the proxy to its destination named. Every read before then waits only for what
    is left of it, so a client that sends one byte a second is closed at it as surely as one
    that sends nothing. Past it, the connection is closed. A relayed connection has no deadline,
    since a held tunnel is legitimate, and the caps bound those instead. After the proxy closes a
    connection, the bridge's relay for it lasts until the client in the jail sends or closes:
    only the bridge's cap bounds that, and it costs the jail's own PID 1, not the host.

  Each lowered limit travels on the host's own line to its program: the proxy's two on its
  config line (`connections`, `handshake_s`), the bridge's in the supervisor's exec request
  (`bridge_limit`). Both lines are written by the host on fds the command never holds. argv was
  not used for three reasons. The supervisor's argv is readable in the jail as `/proc/1/cmdline`.
  The proxy's is `python -I -`, which is how the host finds it. And neither program parses
  arguments: each already reads one closed JSON shape from the host. The embedder's side is
  `EgressLimits` (presentation).

  Grants change while the jail runs, and decisions come back (decision-0009 items 5 and 6,
  TASK-0001.37). Each line on the config pipe after the first is one change, `{kind, host,
  port}`, written whole (far shorter than `PIPE_BUF`) by `RunningProxy.change`, which records it
  with its time under the same lock. Each turn of the proxy's loop applies every whole change
  line before it takes the next connection, and a connection is decided against the grants in
  force when its fd arrived. So a connection the supervisor hands over after a change was
  written is decided against the new grants, and a connection already relaying is never judged
  again: revoking a grant leaves an open tunnel open. The proxy writes each settled decision as
  one envelope line (`source` `egress-proxy`, `event` `egress-decision`, then `seq`, `verdict`,
  `host`, `port`, `reason`; `info` when allowed, `warning` when refused) to its fd 5, the
  decisions pipe, and nothing else is written there: its fds 1 and 2 stay `/dev/null`. A
  request whose destination could not be read is answered `400` and makes no decision, since it
  names none. A thread `RunningProxy.watch` starts drains that pipe for as long as the proxy
  runs, so a proxy whose embedder reads nothing never blocks on it, and keeps at most
  `KEPT_LINES` (1024) lines of at most `LINE_LIMIT` (4096 bytes) for the embedder to take,
  dropping the oldest past that, and a longer line whole: at most 4 MiB per jail. The proxy's
  `seq` shows a gap where lines were dropped. `RunningProxy.end` joins the thread once the proxy
  is reaped, and what was read stays to be taken. The link keeps its proxy once the supervisor
  is closed, so the record and the last decisions stay readable.
- `log.py`: brig's one log envelope and its encoder (decision-0001 rule 14, TASK-0001
  criterion 15, TASK-0001.37). A line is one JSON object, ASCII only: `time` (RFC 3339, UTC, to
  the microsecond, `Z`), `level` (`debug`, `info`, `warning`, `error`), `source` (which of
  brig's programs wrote it) and `event`, first and in that order, then the event's own fields,
  each a JSON scalar. `encode` is the one place a line is made, and refuses a field named like
  the head and a naive time; `decode` reads one back, refusing what `encode` would not write;
  `write` is the one raw write of a line to an fd (the `brig-one-writer` allow list names it
  beside the supervisor's wire). It is standard library only and imports nothing of brig (the
  `brig-standalone-programs` gate), and the proxy's file carries it as a module of its own, so
  the proxy writes exactly the envelope the library reads. The supervisor's wire is its own
  protocol, not a log, and writes no envelope line yet.
- `supervisor/`: the jail's PID 1 on Linux and root supervisor process on Darwin (decision-0002,
  decision-0010). `wire.py` and `program.py` assemble
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
  child, under the same uid, so the supervisor makes itself non-dumpable (`PR_SET_DUMPABLE=0` on
  Linux; `ptrace(PT_DENY_ATTACH, 0, 0, 0)` on Darwin) before the command
  exists, and the bwrap compile drops every capability (`--cap-drop ALL`): the command can
  neither reopen the supervisor's fds through `/proc/1` (absent on Darwin) nor ptrace it, so the
  exit code the host reports is the one `waitpid(2)` gave (decision-0006, decision-0010).

Not yet built: `tether.py` and `sandbox_exec.py`.

## Presentation

`src/brig/presentation/` is the only layer that knows both of the others, and the only one that
raises. `ports.py` states what a driver needs from infra as `Protocol`s, so a test runs a driver
against a fake of the same shape, and holds the readiness outcomes an embedder matches on. A
port speaks domain's values or its own, never infra's: `jail.py`'s real wiring translates
infra's sentinels on the way in. `driver.py` performs a generator's effects through the ports,
for every jail type.

Each jail type's own presentation is its slice (decision-0007 item 5, decision-0010):
`drivers/bwrap.py` (`create_bwrap_jail`) and `drivers/seatbelt.py` (`create_seatbelt_jail`)
each refuse and compile the policy, write the supervisor script (and for Seatbelt, `profile.sb`
in the jail's state directory), start the jail through the driver, and hold its namespace/group
fd for readiness. With
`egress=EgressPolicy(...)` it first refuses a malformed policy through `check_egress_policy`,
whose errors it raises, and an `EnvPolicy` naming a proxy variable
(`PolicyEnvNamesProxyVariable`), before anything is looked at. Then it reads the decision's
source and assembles the proxy (`EgressProxySourceUnreadable` for a broken install), and builds
the supervisor with the bridge, and holds the `EgressPort` to its proxy on the `Jail`
(`jail.py`'s `real_egress_port`, which translates the link's plain data into the domain's values
and its `ProxyEnded` into `JailEgressEnded`). `egress_hosts` is the proxy's resolver seam: a table of names to
addresses, given as data, that the proxy resolves from instead of the host's resolver; every
address is still judged. `egress_limits` is an `EgressLimits(connections, bridge_connections,
handshake_s)`, each defaulting to its program's constant and refused by `check_egress_limits`
(`PolicyEgressLimitOutOfRange`) when it is not above zero or is above that default, before
anything starts (TASK-0049). With no `egress`, nothing new runs and nothing changes. What every jail
type shares is beside it: `jail.py` (the `Jail`, brig's state directory, the real ports'
wiring, and `dismantle`: the verified kill ladder for a process that exists, then removing the
script, the channel directory and the fds, and releasing the placeholders only on a group read
gone, the one cleanup `destroy_jail` and a failed create both run; it raises nothing, and hands
back what its ladder or the supervisor's close raised, a raising ladder reading as a group not
verified gone, for its caller to attach to what it raises, TASK-0046), `api.py` (checking an egress policy, changing a running jail's grants and reading what its proxy
decided, reserving channels, readiness, waiting, interrupting the command with `SIGINT` through
its supervisor, teardown) and `report.py` (a report as text).

A running jail's egress is the embedder's to change and to read (decision-0009 items 5, 6 and 8,
TASK-0001.37). `allow_egress(jail, destination)` and `revoke_egress(jail, destination)` refuse a
jail with no egress proxy with `JailHasNoEgress` (one created without an `EgressPolicy`, or with
a caller's own `supervisors`), then a malformed destination exactly as `check_egress_policy`
refuses one, before anything is sent, then send the change; the jail is not restarted, and the
next connection is decided against the new grants. A revoke does not cut a connection already
open (each is judged once, when it names its destination); only `destroy_jail` ends what is open.
Once the proxy has ended (`run_jail` saw the
command done, or `destroy_jail` ran) a change is `JailEgressEnded`, sent and recorded nowhere.
`egress_decisions(jail)` returns, without blocking, an iterator over the decisions that arrived
since the last call, each handed back once, so an embedder can poll it between its own events
and ask its person about a refusal; a cursor over every decision was not chosen, since it would
keep history for a reader that may never come, which is the memory this bounds. Each value
carries the envelope line verbatim, for an embedder that keeps a log of its own: the library
writes the line nowhere. `egress_record(jail)` is the policy as created and every change since,
and `render(jail.report, egress_record(jail))` states both after the claims, one line per
change with its time, and what is granted now. With an egress policy the report's `network`
claim is `NETWORK_EGRESS_CLAIM`: the command reaches only the destinations the policy grants,
and only through the proxy, capped like `network` by the socket half of TASK-0043, and naming
the two gaps the proxy leaves (an HTTP `CONNECT`'s authority is judged, never the TLS SNI inside
it, so a granted CDN can front for another name; the bytes inside a granted connection are not
inspected). *Held by* `tests/e2e/test_egress_live_battery.py` (refused, allowed and reached
with no restart, revoked and refused while an open tunnel stays, each decision and its line),
`tests/e2e/test_report_battery.py` (the egress claim held to what it measures, and the rendered
record), `tests/e2e/test_log_envelope.py`, `tests/integration/test_egress_live_grants.py` and
the unit tests of `egress_after`, `egress_reason` and the ceilings.

An embedder talks to a channel only over the connection readiness verified. `await_channel_ready`
returns `ChannelReady(connection)`, the verified socket still open, and the embedder owns it and
closes it; it never dials the reservation's `bound_path` itself. The jail can write its channel
directory, so once readiness has passed it can replace its socket with a symbolic link to any
socket the embedder's user can reach on the host, and a plain connect follows the link
(TASK-0001.34). Readiness is a property of one connection (decision-0005 item 1): a second
connection is a second `await_channel_ready`. Only the attempt that reads ready leaves a socket
open. Readiness itself never dials as the embedder what the jail planted, and never outlasts its
deadline (law 7): `create_bwrap_jail` and `create_seatbelt_jail` open an fd on the channel directory as soon as it is
made and hold it on the `Jail` until `destroy_jail` closes it, each attempt opens the
reservation's name beneath that fd through no link, refuses a link there as `PEER_OUTSIDE_JAIL`
without connecting, and connects without blocking, so a jail that fills its own listen backlog
reads not ready until the deadline instead of holding the embedder (TASK-0045). *Held by*
`tests/e2e/test_channel_readiness_battery.py` (the swap after readiness),
`tests/e2e/test_channel_readiness_refusals.py` (every other outcome closes its socket),
`tests/e2e/test_channel_readiness_dial.py` (the deadline against a full backlog, and a planted
link never dialled), `tests/e2e/test_channel_readiness_beneath.py` and
`tests/e2e/test_seatbelt_channels.py`. `errors.py` names
every exception an embedder can see, one per failure, so an embedder handles brig's own types
and never infra's: a host that refuses brig's own state directory, its empty directory or the
supervisor script before a jail starts is `StateDirectoryWriteFailed` (TASK-0046), a path the
policy or stdio names (or the interpreter) that the host will not let brig inspect is
`PolicyPathUninspectable`, and brig's own supervisor source it cannot read is
`SupervisorSourceUnreadable`, read before the script is made so a broken install is never
reported as the state directory (TASK-0047). *Held by*
`tests/integration/test_create_inspection_errors.py`. `src/brig/__init__.py` re-exports exactly this layer's surface and the
domain's plain data, nothing from infra.

(decision-0001's layout had a `proxy_main.py` entry point
here; the proxy is instead one assembled file run from its stdin, so it never imports brig.)
