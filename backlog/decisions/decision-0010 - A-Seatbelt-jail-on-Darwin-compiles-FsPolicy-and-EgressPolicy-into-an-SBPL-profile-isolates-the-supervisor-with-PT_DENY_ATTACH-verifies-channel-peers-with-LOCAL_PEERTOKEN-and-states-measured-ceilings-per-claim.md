---
id: decision-0010
title: >-
  A Seatbelt jail on Darwin compiles FsPolicy and EgressPolicy into an SBPL
  profile, isolates the supervisor with PT_DENY_ATTACH, verifies channel peers
  with LOCAL_PEERTOKEN, and states measured ceilings per claim
date: '2026-11-10 20:05'
status: accepted
---
## Context

TASK-0061 (for TASK-0001's Seatbelt slice on Darwin): an embedder running on macOS needs the same
supervisor, request channels, `FsPolicy`, `EnvPolicy`, `EgressPolicy`, and honest per-claim
report (`jail.report`) that `bwrap` provides on Linux, backed by `/usr/bin/sandbox-exec` and XNU's
Seatbelt MAC policy.

Four design questions had to be settled by measurement on Darwin before writing code:
1. **How `FsPolicy` compiles to SBPL.** Seatbelt has no mount namespace; it evaluates SBPL rules
   against resolved paths, the last matching rule winning, after `(version 1)` and
   `(deny default)`.
2. **How the supervisor is protected inside the jail on Darwin.** Linux uses `PR_SET_DUMPABLE=0`
   plus an unshared user/PID namespace with all capabilities dropped (decision-0006), and closes
   inherited fds 3, 4, and 5 before spawning children. Darwin has no `prctl` and no PID namespace.
3. **How channel readiness and peer verification work on Darwin.** Linux uses `SO_PEERCRED` plus
   `/proc/<pid>/ns/pid` (decision-0005). Darwin has no `/proc` and no PID namespace.
4. **What grade ceilings Seatbelt reaches per claim (`fs_write`, `fs_read`, `network`, `env`,
   `channel_exclusivity`), held to empirical e2e measurement on Darwin.**

*Revised 2026-11-11 (TASK-0061, second worker).* The first version of this record was written
before the code was run and stated several things that were not measured, some of them false: it
cited `(import "system.sb")`, which the code never emitted, as the reason `fs_read` is
best-effort; it named `(allow signal (target same-sandbox))` where the code allowed every signal;
and it did not mention that the code allowed every Mach service, all of `/dev` for writing, and
an outbound rule filtered on the local port. Every claim below was measured on macOS 27.0.1
(`/usr/bin/sandbox-exec`, CPython 3.15.0) by scratch probes and is now held by the e2e tests
named. The body was corrected by hand, since `backlog decision edit` sets only the status, as
decision-0009's body was written after its `create`.

## Decision

1. **SBPL compilation (`brig.domain.jail_types.seatbelt`) and template-string rendering
   (decision-0001 rule 16).**
   - **Header**, every line measured (`_HEADER_LINES`):
     - `(version 1)`, `(deny default)`. No `(import "system.sb")`: CPython, `sh` and `git` start
       without it, and without it `/etc/passwd` and `/usr/lib/dyld` are unreadable unless the
       policy reads them. (The old SPEC's "deny default alone aborts even `/bin/echo`" does not
       hold once the root directory is readable, below.)
     - `(allow process-exec process-fork sysctl-read)`. `sysctl-read` also lets the jail read
       every host process's arguments (`KERN_PROCARGS2`; measured, environment not shown).
     - `(allow signal (target same-sandbox))`. Unfiltered, a jail sent `SIGTERM` to a host
       process of the same user and killed it; filtered, `kill` of a host process or another
       jail's supervisor is `EPERM`, and the jail still signals its own children.
     - No system call is refused by number. *Amended 2026-11-11 after review:* this revision
       first refused `SYS_setsid` and `SYS_setpgid`, so a command could not leave the group
       `destroy_jail` kills. It held nothing: `os.posix_spawn(..., setpgroup=0)` or
       `setsid=True` left the group anyway (the reviewer's repro, measured again here: the
       spawned shell outlived `destroy_jail` and wrote its file 3 seconds later), and the refusal
       cost every daemon its session. Teardown now finds the jail's processes by their sandbox
       (item 2), so the refusal is dropped and a jailed `setsid` works.
     - `(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo"))`, nothing
       else of Mach. Unfiltered, `pbpaste` in a jail read the host's pasteboard; with only the
       directory lookups, `pwd`, `grp`, `whoami`, `id`, `git`, `ssl` and `subprocess` still
       work and `bootstrap_look_up` of the pasteboard is refused. Every other service is a route
       the compile could not grade, so the profile names the one it can.
     - `(allow file-read-data file-read-metadata (literal "/"))`: without `file-read-data` on
       `/`, `dyld` aborts every process (`SIGABRT`). It lists the names at `/`.
     - `(allow file-read* file-write-data ...)` on `/dev/null`, `/dev/zero`, `/dev/stdin`,
       `/dev/stdout`, `/dev/stderr` and `/dev/fd`, and `(allow file-read* ...)` on `/dev/urandom`
       and `/dev/random`. With `file-write-data` on all of `/dev`, a jail opened the user's
       terminal for writing. No `file-ioctl`: nothing measured needed it.
   - **Read and write roots (shallowest first by path depth, at both the path and where it
     resolves when a link such as `/var -> /private/var` or `/tmp -> /private/tmp` differs):**
     - For every root, `(allow file-read-metadata (literal "<dir>"))` on each ancestor directory
       from `/` down, so `execvp` and `realpath` reach the root without listing its ancestors.
     - A readable root emits `(allow file-read* (subpath "<root>"))`, and, nested in a writable
       root, `(deny file-write* (subpath "<root>"))` after it.
     - A writable root emits `(allow file-read* file-write* (subpath "<root>"))`.
   - **Carve-outs after roots:** a write deny emits `(deny file-write* (subpath "<path>"))`, a
     mask `(deny file-read* file-write* (subpath "<path>"))`. brig's state directory is masked
     after every policy rule, then this jail's supervisor script is allowed read-only and its
     channel directory read-write, so the command reaches neither another jail's script, its
     profile, nor its channels.
   - **Pins and placeholders** (old SPEC decisions 207 and 208): every writable root other than
     `/`, and every directory strictly between a writable root and a carve-out (a deny, a mask, a
     nested readable root, the state directory), is pinned with
     `(deny file-write-unlink (literal "<dir>"))`; an absent one is made before the jail starts
     (`placeholders.hold`). Measured: without the pins, a jailed command renamed the directory
     above a write deny, wrote beneath the new name, and renamed it back.
   - **Network:** `(deny default)` refuses every network operation; no `(deny network*)` line is
     needed. With a channel, `(allow network-bind network-outbound (subpath "<channel_dir>"))`.
     Measured: a subpath-filtered `network-bind` binds in the channel directory (the old SPEC's
     "`network-bind` must be unscoped" does not reproduce on 27.0.1), and a connect to a host
     Unix socket in a readable root, a bind outside the channel directory, TCP, UDP and name
     resolution are all refused.
   - **Egress:** with an `EgressPolicy`, `(allow network-bind network-inbound (local tcp
     "localhost:<port>"))` for the supervisor's bridge and `(allow network-outbound (remote tcp
     "localhost:<port>"))` for the command. Measured: the first version also allowed
     `network-outbound` under the `local` filter, and with it a jailed command bound its source
     port to the bridge port and connected to `1.1.1.1:80`; split as above, that is refused and
     both bridge listeners are still reachable. SBPL accepts only `localhost` or `*` as the host
     (`127.0.0.1` is a parse error), and `localhost` matches every local address on both sides:
     `[::1]:<port>` and the LAN address at `<port>` connect, `127.0.0.1:<other port>` does not,
     and a jailed command can listen on `0.0.0.0:<port>` with `SO_REUSEADDR` beside the
     supervisor's listeners.
   - **Template-string rendering:** `render_profile` renders each rule through `_render_atom`,
     which accepts only a `string.templatelib.Template`, escapes `\` and `"` in every
     interpolated value, and refuses a NUL byte.

2. **Supervisor protection on Darwin (`brig.infra.supervisor.program`).**
   - `_make_undumpable()` on Darwin calls `ptrace(PT_DENY_ATTACH, 0, 0, 0)`. Measured: a jailed
     command that calls `ptrace(PT_ATTACHEXC, <supervisor>)` is killed with `SIGSEGV`, and the
     host reads exit -11. Without `PT_DENY_ATTACH` the attach already fails with `EPERM` and
     `task_for_pid` with `KERN_FAILURE` on this host, so it is a second wall, not the only one.
   - The supervisor closes fds 3, 4 and 5 in the command (measured: none is open there), and
     Darwin has no `/proc/<pid>/fd` to reopen them through.
   - `sandbox-exec -f <profile> python -I <supervisor.py>` execs in place, so the supervisor is
     the jail's root process and leads its own session and process group.
   - What differs from Linux: the supervisor shares the command's sandbox, so the command can
     signal it. Measured: a command that sends its supervisor `SIGKILL` makes `run_jail` raise
     `JailExitUnknown`; the exit code is lost, never forged, and `destroy_jail` still ends the
     jail.
   - **Teardown finds every process of the jail by its sandbox, freezes it from inside, and
     kills it (`brig.infra.members`).** *Revised 2026-11-11 after the re-review.* Darwin has no
     PID namespace: a jailed process can leave the supervisor's group (`posix_spawn` with
     `setpgroup` or `setsid`), and once its parent exits it is launchd's child, so neither a
     group kill nor a walk of the process tree finds it. What it cannot shed is its sandbox.
     - *Finding:* each jail gets two empty files in brig's state directory, a mark and a decoy
       beside it; its profile allows `file-read-metadata` on its own mark after the state
       directory's mask, which refuses the decoy. `sandbox_check` (a libSystem export with no
       declaration in the SDK's headers, so private interface Apple may change) asks what a
       given process's profile decides: a process of the embedder's uid that is sandboxed,
       allowed the mark and refused the decoy is the jail's. Measured: it tells jail A's process
       from jail B's and from an unsandboxed one, and still finds A's process after it called
       `setsid`. It answers "refused" for a path that does not exist and for a process that is
       gone (pinned by `test_seatbelt_members.py`). On arm64 its variadic path reaches it only
       when ctypes places it on the stack, behind five unused fixed arguments (without them every
       check answered "refused"); x86_64 is not measured.
     - *Why a sweep from the host is not enough:* a first version scanned and killed until a scan
       found nothing. The re-review's repro (fork away, `setsid`, then fork and exit in a loop for
       8 s, then write a file) beat it: a scan takes about 3 ms over about 1,000 processes, and
       the chain's newest pid is always one the scan has not judged yet. `destroy_jail` raised
       after 1 s and the survivor wrote its file 8 s later.
     - *Freezing from inside:* `kill(-1, sig)` from a jailed process reaches, under
       `(allow signal (target same-sandbox))`, every process of that sandbox and the caller
       itself, and nothing outside it. Measured: it reached neither an unsandboxed parent nor a
       process started separately under the same profile file (a second `sandbox-exec` is a
       sandbox of its own), and the caller received its own signal. So the killer must already be
       inside the jail, and one `kill(-1, SIGKILL)` pass dies with it: measured against the
       fork loop, one pass missed the chain in 1 run of 15. `SIGSTOP` can be repeated. The
       supervisor starts a freezer before the command (`program._FREEZER`), which forks away and
       leads a session of its own, so it outlives its command, holds none of the supervisor's
       fds, and is reaped by no one in the jail. At teardown, before the group's kill ladder,
       the host scans the jail, sends the freezer (found by its `brig-teardown-freezer`
       argument) `SIGUSR1`, which makes it call `kill(-1, SIGSTOP)`, and continues it with
       `SIGCONT` for another pass while a scan still finds a member running. A stopped process
       cannot fork, so once two scans in a row find the same members, all stopped, each is
       killed. A scan in which a process it listed vanished before it was judged is not
       trusted, since a running fork chain always shows as one of those. Measured: the repro
       now ends in 30 to 70 ms, and its file is never written (`test_seatbelt_journey.py`);
       without the freeze, the same test fails with `JailTeardownFailed`.
     - *What does not hold:* every SBPL signal target that lets the freezer reach the jail's
       orphans (`same-sandbox`) lets the command signal the freezer too; `children` reaches only
       direct children, `self` and `others` only the caller, and `pgrp` the caller's process
       group, which a process that left it is out of (measured). So a command that kills its freezer first, and then forks in a loop,
       defeats the freeze. Teardown then kills each member a scan finds, with its process group,
       which ends a jail that does not fork in a loop and races one that does. If one is left
       when `kill_grace_s` has passed, `destroy_jail` raises `JailTeardownFailed` naming a
       process that left the group (`members_left`), apart from a live group; the survivor is
       still sandboxed, and its mark and decoy are kept. Every later `create_seatbelt_jail` and
       `destroy_jail` sweeps the kept marks again (`reap_kept`) and removes each once nothing
       carries it. A command that forks in a loop forever after killing its freezer can outlive
       every sweep; that residual is named here and in the spec, and teardown reports it rather
       than claiming the jail gone.
     - *Canary:* a wrong `sandbox_check` call reads every process as no member, and a sweep that
       finds nothing would look like success. So `create_seatbelt_jail` waits until the jail's
       running supervisor is found carrying the profile, and raises `JailMembersUnverifiable`
       (the jail torn down first) if it is not; and `destroy_jail` asks again while the
       supervisor runs, raising the same after its group kill if it is not found. A supervisor
       that has exited tells the canary nothing, either way.
     - A pid that exited and was reused between a scan and its kill could be signalled; the two
       are microseconds apart and Darwin hands out pids in rising order.

3. **Channel readiness and peer verification on Darwin (`brig.infra.sockets`).**
   - `open_directory` opens the channel directory `O_RDONLY | O_DIRECTORY | O_NOFOLLOW` (no
     `O_PATH` on Darwin), and `channel_ready` reads its path back with `fcntl(F_GETPATH)`.
   - Before the connect, the name is `lstat`ed beneath the directory fd: a link is
     `PEER_OUTSIDE_JAIL` without a connect, anything but a socket is not ready. After the
     connect, the inode is checked again.
   - The peer's `audit_token_t` comes from `getsockopt(SOL_LOCAL=0, LOCAL_PEERTOKEN=0x006, 32)`.
     Measured against a forked listener of known pid: the eight words are
     `(auid, euid, egid, ruid, rgid, pid, asid, pidversion)`, the pid at index 5 and the
     pidversion at index 7, equal to `proc_pidinfo(PROC_PIDUNIQIDENTIFIERINFO)`'s `p_idversion`;
     `proc_pidinfo(PROC_PIDTBSDINFO)`'s `pbi_pgid` equals `os.getpgid`.
   - The peer is the jail's when its `euid` is the embedder's, it is alive and no zombie, its
     `p_idversion` is the token's (the pid was not reused), and its process group is the
     supervisor's, held in `jail_namespace_fd`. POSIX lets `setpgid` join only a group in the
     caller's own session, so no process outside the jail's session can join it; a jailed
     listener that left the group (a daemon) is refused, never let in. Measured: a listener the
     host put in the jail's channel directory is `ChannelRefused`.
   - Not measured here: the first version's statement that `LOCAL_PEERTOKEN` reads `EINVAL` once
     the listener has exited and been reaped. Either way such a peer fails the `proc_pidinfo`
     lookup and is refused.
   - A residual of Darwin's: the connect goes to the socket's path, so a link the jail swaps in
     between the `lstat` and the connect is followed. The peer check then refuses what answered,
     but the embedder has dialled it; Linux connects through the `O_PATH` fd and has no such
     window.

4. **Measured grade ceilings on Darwin (`seatbelt.ceilings`).**
   - **`fs_write`:** `ENFORCED` when no non-writable subpath (a deny, a mask, a nested readable
     root, brig's state directory) lies beneath a writable root; else `BEST_EFFORT`, since
     Seatbelt judges a path, not the file at it, and the host renaming or linking an entry on the
     way moves what lies beneath it. Measured: a write outside the writable root, a hard link
     from it to a read-only file, a rename of the directory above a write deny, and opening a
     terminal for writing are refused, each beside an unjailed control that does it.
   - **`fs_read`:** `BEST_EFFORT` whatever the policy: the jail lists the names at `/`, reads the
     metadata of every ancestor of a root, reads host processes' arguments through `sysctl`,
     reads the hardware registry (`ioreg` in a jail prints what it prints outside, the machine's
     serial number among it; opening a driver is refused), and looks up the host's users and
     groups (all measured), and a mask matches a path, so a host
     hard link or rename of a masked file shows it under another name. Measured: a masked file
     and a file outside every readable root are refused.
   - **`env`:** `ENFORCED` (the supervisor spawns every command with the allowed environment
     alone; measured).
   - **`channel_exclusivity`:** `VIOLATED` when an undeclared writable path is shared with the
     host, else `ENFORCED`: Seatbelt refuses a dial of a host Unix socket inside a readable root,
     a signal to any process outside the jail, and every Mach service but the directory lookups.
     Measured: each refused beside its unjailed control, and another jail neither dials nor binds
     in a jail's channel directory.
   - **`network`:** without an `EgressPolicy`, `ENFORCED` (TCP, UDP, host Unix sockets and Mach
     refused; measured). With one, `BEST_EFFORT` (`SEATBELT_NETWORK_EGRESS_CLAIM`): a host
     service listening at the bridge port on any local address other than the supervisor's own
     is reachable past the proxy, and the command can listen at the bridge port on the wildcard
     address, reachable from the network. On Darwin the supervisor's `[::1]` bind is required,
     so `[::1]:<port>` is never some host program's. The bridge port is fixed at 3128 on the
     host's shared stack, so one egress jail at a time runs per host. Measured: a second's
     supervisor cannot bind it and exits before its command starts, and `run_jail` raises
     `JailExitUnknown`.

## Consequences

- `brig.domain.jail_types.seatbelt` and `brig.presentation.drivers.seatbelt` implement the Darwin
  Seatbelt jail (`create_seatbelt_jail`), exported from `brig` with the `SEATBELT_*` claims.
- `brig.infra` works on both Linux and Darwin (`placeholders`, `sockets`, `supervisor`, `proxy`,
  `processes`).
- Every Seatbelt ceiling in `jail.report` is held by the e2e tests
  `tests/e2e/test_seatbelt_battery.py`, `test_seatbelt_channels.py`, `test_seatbelt_egress.py`,
  `test_seatbelt_journey.py` and `test_seatbelt_supervisor.py`, which run on a Mac and skip on
  Linux; the profile's shape by `tests/unit/test_seatbelt_compile.py` and
  `test_seatbelt_ceilings.py`. Teardown by `test_seatbelt_journey.py`'s escape tests and
  `tests/integration/test_seatbelt_create.py`.
- Open: the bridge port's fixed number on a shared stack (one egress jail per host); the
  readiness dial's path window above; and a command that kills its freezer and then forks in a
  loop forever, which outlives teardown (reported, never claimed gone; item 2).
