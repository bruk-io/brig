---
id: TASK-0061
title: A Seatbelt jail for darwin
status: In Progress
assignee: []
created_date: '2026-11-10 17:16'
updated_date: '2026-11-11 15:58'
labels:
  - darwin
  - security
  - size-8
dependencies: []
modified_files:
  - src/brig/domain/jail_types/seatbelt.py
  - src/brig/presentation/drivers/seatbelt.py
  - src/brig/presentation/jail.py
  - src/brig/__init__.py
  - src/brig/infra/supervisor/program.py
  - src/brig/infra/sockets.py
  - src/brig/infra/placeholders.py
  - src/brig/infra/proxy/launch.py
  - src/brig/infra/proxy/program.py
  - src/brig/infra/supervisor/link.py
  - docs/spec/index.md
type: task
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From bh-02's port onto bruk-io/brig v0.1.0: this brig has no darwin jail, so bh-02's runner:confined refuses on a Mac and points at runner:unconfined (bh-02 TASK-0196). The old in-repo brig (bh-02 commit d0c3a416 (its in-repo libs/brig, removed by bh-02's port to this brig), libs/brig/src/brig/mech and core) had a Seatbelt jail, measured on a Mac, with decision-207 (its Seatbelt pins) and decision-208. Owner of bh-02, 2026-10-31: built when a Mac run can prove it; on 2026-11-10: fine for the Mac jail not to work for now.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On darwin, a jail confines a process's writes and network as the spec grades them, measured on a Mac
- [ ] #2 bh-02's runner:confined runs jailed on a Mac again
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Taken over 2026-11-11 from an agent that ran out of quota. Everything inherited (decision-0010, infra Darwin support, the uncommitted seatbelt jail type and driver) is treated as unreviewed; its claims are re-measured on this Mac (macOS 27.0.1, /usr/bin/sandbox-exec, CPython 3.15.0).

Measured before planning (scratch probes, then pinned by e2e tests):
- The profile does not import system.sb, and Python, sh and git start without it; /etc/passwd and /usr/lib/dyld are then unreadable. decision-0010's reason for fs_read BEST_EFFORT (system.sb's grants) is false.
- Unfiltered (allow signal) let a jail kill a host process of the user; (target same-sandbox) refuses it and still lets a jail signal its own children.
- Unfiltered (allow mach-lookup) let a jail read the host pasteboard; with only com.apple.system.opendirectoryd.libinfo it is refused and pwd, grp, whoami, git, ssl and subprocess still work.
- (deny syscall-unix (syscall-number SYS_setsid SYS_setpgid)) refuses both, so a command cannot leave the group destroy_jail kills.
- LOCAL_PEERTOKEN (0x006, 32 bytes): pid at [5], pidversion at [7] equal proc_pidinfo's; pbi_pgid equals os.getpgid.
- PT_DENY_ATTACH: an attaching child is killed with SIGSEGV; without it attach and task_for_pid already fail.
- Unix sockets: bind and connect allowed in the channel directory under a subpath-filtered network-bind; a host socket in a readable root, a bind outside, TCP, UDP and DNS refused.
- (remote tcp "localhost:P") also matches [::1]:P and the LAN address at P.

### Order of work
1. Domain (src/brig/domain/jail_types/seatbelt.py): narrow the header to the measured lines; fix the egress rule (no outbound under a local filter); _render_atom and the shared-path helpers private; claims' text and ceilings' docstring to the measured reasons.
2. Infra (src/brig/infra/supervisor/program.py): on darwin the supervisor's [::1] bridge bind is required, since the profile's localhost filter reaches [::1].
3. Presentation (src/brig/presentation/drivers/seatbelt.py, src/brig/presentation/jail.py, src/brig/__init__.py): lint fix for the Raises section; the profile written owner-only; export create_seatbelt_jail and the SEATBELT_* claims.
4. Tests: unit (tests/unit/test_seatbelt_compile.py, test_seatbelt_ceilings.py), integration (tests/integration/test_seatbelt_create.py), e2e on darwin (tests/e2e/test_seatbelt_journey.py, test_seatbelt_battery.py, test_seatbelt_channels.py, test_seatbelt_egress.py, test_seatbelt_supervisor.py), each attack beside an unjailed control, each report held with at_most.
5. Correct decision-0010's unmeasured or false claims and docs/spec/index.md where it repeats them.
6. uv run just done and uv run just test-e2e on this Mac; report in implementation notes and .gemini-report.md.

Changed from the first version of this plan: a per-jail bridge port was planned for step 2 and not built. It is a design change on a shared stack; the fixed port's limits are recorded in decision-0010 and the notes as open, for Bruk.

### Risks
- A header line narrowed too far breaks programs beyond CPython, sh and git (larger tools may need more Mach services or /dev nodes); each addition needs its own measurement.
- Refusing setsid and setpgid breaks commands that daemonise; chosen for teardown completeness, flagged for Bruk.
- Linux CI is not run from here: the only shared change for Linux is guarded by sys.platform == "darwin", and the new integration tests start nothing.
- Egress on the host's shared stack stays BEST_EFFORT: one egress jail per host on port 3128, and SBPL's localhost matches every local address.

### Proof
- Every header narrowing, the egress rule, the pins, the masks, the peer group check, PT_DENY_ATTACH and the profile cleanup is mutation-checked: putting each weakness back fails its test.
- uv run just done exits 0 and uv run just test-e2e exits 0 on this Mac, with no seatbelt test skipped.

### Amendment after the pre-merge review (2026-11-11)
The setsid/setpgid refusal above did not hold (posix_spawn with setpgroup or setsid left the group) and is dropped. Teardown instead kills every process whose sandbox allows the jail's mark and refuses its decoy (src/brig/infra/members.py, a MembersPort through dismantle and destroy_jail), measured by the review's repro and its setsid variant as e2e tests. The Risks line about daemons no longer applies; the new risk is that sandbox_check is private interface, reached through ctypes with an arm64 argument layout measured only here.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Report of the second worker (2026-11-11), measured on macOS 27.0.1 with /usr/bin/sandbox-exec, revised after the pre-merge review's must-fix list. Not pushed; left In Progress for a reviewer. AC #1 is ready for review; AC #2 is bh-02's and was not attempted.

## Commits

Inherited from the first worker (reviewed here and corrected where wrong):
- `8b5c01d` backlog: Add decision decision-0010
- `30496fc` Update task TASK-0061
- `06788aa` docs(spec,arch): record decision-0010 and specify Darwin Seatbelt slice
- `d6348d2` feat(infra): support Darwin in placeholders, sockets, supervisor, and proxy

Mine:
- `93a9f7b`, `4714566` and the last `Update task TASK-0061` commits: the plan and these notes,
  written by the `backlog` CLI
- `26d1197` feat(seatbelt): a Seatbelt jail type and driver for darwin, with a measured profile header
- `4b55998` test(seatbelt): e2e batteries on a Mac, each attack beside its unjailed control
- `49ee409` docs(seatbelt): correct decision-0010 and the spec to what was measured
- `0eb97e3` fix(seatbelt): teardown finds every process that carries the jail's profile (the
  review's must-fix list: teardown, the hardware registry, the egress test's teeth)
- the commit after it: docs only, naming `sandbox_check` as private interface

## Results on this Mac

After the review's fixes (`0eb97e3`):
- `uv run just done`: exit 0, "done: all steps passed". Lint, typecheck and gates pass;
  pypeeker rule tests 51 passed; unit 418 passed; integration 96 passed and 2 skipped, both
  passes; e2e 119 passed and 118 skipped; docs, architecture validate and architecture lint pass.
- `uv run just test-e2e`: exit 0, 119 passed, 118 skipped, 0 failed. The 118 skips are the same
  Linux-only tests as before this work (bwrap, procfs, `SO_PEERCRED`, root); no seatbelt test
  skips here. Before this work it was 86 passed, 118 skipped.
- Linux CI was not run (no push). See "What Linux shares" below.

## What Linux shares, and how each change is kept to darwin

Every change to code that also runs on Linux, and its guard:
- `infra/placeholders.py`: extended attributes go through `os.setxattr`/`os.getxattr` when `os`
  has them (it does on Linux, so Linux runs the same call as before), else through libc with
  `XATTR_NOFOLLOW`. A record's start time is read from `proc_pidinfo` only when
  `sys.platform == "darwin"`, else from `/proc/<pid>/stat` as before.
- `infra/proxy/launch.py`: the supervisor-to-proxy socketpair is `SOCK_SEQPACKET` as before, and
  `SOCK_STREAM` only when that raises `EPROTONOSUPPORT` (Darwin); any other error raises as
  before.
- `infra/proxy/program.py`: host local addresses come from `/proc/net` as before, and from
  `getifaddrs` only when neither `/proc/net` file exists and `sys.platform == "darwin"`.
- `infra/sockets.py`, signalling: `signal_jail_pid1` takes the darwin path only when
  `sys.platform == "darwin"` and `/proc` is absent. `_signal_checked` now looks `os.pidfd_open`
  and `signal.pidfd_send_signal` up with `getattr`; on a Linux CPython that has them (every
  supported one), unchanged. On one that lacked them it would now answer "not sent" where it
  raised `AttributeError` before.
- `infra/sockets.py`, channel readiness: `channel_ready` takes the darwin path only when
  `sys.platform == "darwin"`; `jail_pid1_namespace` likewise, and only with `/proc` absent.
  `open_directory` and the Linux readiness use `getattr(os, "O_PATH", os.O_RDONLY)`, which is
  `O_PATH` on Linux as before. New module-level `ctypes` structures are definitions only.
- `infra/supervisor/link.py`: the directory walk uses the same `O_PATH` `getattr`, `O_PATH` on
  Linux.
- `infra/supervisor/program.py`: `PT_DENY_ATTACH` only when `sys.platform == "darwin"`, else
  `PR_SET_DUMPABLE` as before; a failed `[::1]` bridge bind raises only on darwin, else is
  skipped as before.
- `infra/members.py` (new): answers "no members" off darwin; called only by `dismantle` for a
  jail with a member mark, which only `create_seatbelt_jail` makes.
- `presentation/jail.py` and `api.py`: `dismantle` also removes a script's `.sb` profile, `.mark`
  and `.decoy` when present (none exists for a bwrap jail), and runs the member sweep only with
  a mark; `destroy_jail` gained a `members` port, defaulting to the real one.

## Grades on darwin, and what measured each

Each attack runs unjailed as a control that shows it works on this host, then jailed, where it
must be refused; the jail's report is held to the measured grade with `at_most`.

| Claim | Grade | Measured by |
|---|---|---|
| `fs_write` | `ENFORCED`; `BEST_EFFORT` with a deny, mask, nested readable root or the state dir beneath a writable root | write outside the project, hard link out to a read-only file, rename of the directory above a write deny (old SPEC decision-207), open of the user's terminal for writing (`test_seatbelt_battery.py`) |
| `fs_read` | `BEST_EFFORT` always | masked secret and a file outside every readable root refused; the reasons it is no better pinned too: the jail lists `/` and reads a host process's argv through `sysctl` (`test_seatbelt_battery.py`) |
| `network` (no egress) | `ENFORCED` | TCP and UDP to a host listener, a host Unix socket in a readable root, a Mach service (`test_seatbelt_battery.py`) |
| `network` (egress) | `BEST_EFFORT` | granted only through the bridge, a direct connect refused, a source port bound to the bridge's refused, an ungranted CONNECT refused by the proxy (`test_seatbelt_egress.py`) |
| `channel_exclusivity` | `ENFORCED`; `VIOLATED` with an undeclared writable root | host Unix socket, signals to a host process and to another jail, a Mach service, another jail dialling or binding in a jail's channel directory (`test_seatbelt_battery.py`, `test_seatbelt_channels.py`) |
| `env` | `ENFORCED` | allowed variable seen, unallowed absent (`test_seatbelt_journey.py`) |

Also measured: a verified channel peer (`ChannelReady`), a listener the host put in the channel
directory refused, interrupt delivered, timeout, cwd, no supervisor fd in the command, ptrace of
the supervisor kills the command (`test_seatbelt_journey.py`, `test_seatbelt_channels.py`,
`test_seatbelt_supervisor.py`).

## Teardown on darwin

Darwin has no PID namespace. A jailed process can leave the supervisor's process group
(`posix_spawn` with `setpgroup=0` or `setsid=True`; the review's repro, which also beat the
`setsid`/`setpgid` refusal I had added), and once its parent exits it is launchd's child, so
neither a group kill nor a walk of the process tree finds it. What it cannot shed is its sandbox.

How it works now (`infra/members.py`, through a `MembersPort`): each Seatbelt jail gets an empty
mark and decoy file beside its script in brig's state directory, and its profile allows
`file-read-metadata` on its own mark after the state directory's mask, which refuses the decoy.
After the group's kill ladder, `destroy_jail` lists every process of the user (`proc_listpids`,
`proc_pidinfo`) and asks `sandbox_check` what each one's profile decides. It `SIGKILL`s every
process that is sandboxed, allowed the mark and refused the decoy, and looks again until a look
finds none. If one is still alive after `kill_grace_s`, teardown raises `JailTeardownFailed` and
keeps the mark. The mark and decoy are removed once none is left.

What measured it:
- Scratch probes: `sandbox_check` tells jail A's process (mark A allowed, B refused) from jail
  B's (the reverse) and from an unsandboxed one, and still finds A's process after it called
  `setsid`. The paths must exist: for a missing path it answers "refused" for everything. On
  arm64 the variadic path reaches it only when ctypes places it on the stack, behind five unused
  fixed arguments: without them every check answered "refused". x86_64 is not measured.
- `test_seatbelt_journey.py`: the review's exact attack and its `setsid=True` variant leave no
  process alive and no `after` file 4 s later. The control half shows the escaped shell is alive
  and out of the jail's group before teardown. Another test shows that destroying one jail
  leaves another jail's process and a host process running.
- `tests/integration/test_seatbelt_create.py` (with a fake `MembersPort`): a member left alive
  fails teardown and keeps the mark; a clean sweep removes mark and decoy; a failed create leaves
  no member files.
- Mutation: with the sweep disabled, the two escape tests and the orphan test fail.

**`setsid`/`setpgid`: dropped.** The refusal held nothing (`posix_spawn` went around it) and cost
every daemon its session, and teardown no longer needs it. A jailed `setsid` now works, held by a
test. The channel peer check still requires the listener's process group to be the jail's, so a
listener that left the group is refused (fail-closed), never let in.

## Other review fixes

- **The hardware registry is readable.** Measured: jailed `ioreg -c IOPlatformExpertDevice`
  prints what it prints outside, the serial number included. It is named among the `fs_read`
  leaks in the claim, the ceilings, decision-0010 and the spec, and pinned in
  `test_the_reasons_reads_are_only_best_effort_are_real`.
- **The source-port egress test has teeth.** It connects off the host (`1.1.1.1:80`) from a
  socket bound to the bridge's port, fails only when the connect succeeds, and prints the errno
  (jailed: `errno 1 (Operation not permitted)`). With the old rule restored it fails on the
  attack itself: "a jailed socket bound to the bridge's port reached ('1.1.1.1', '80'): connected
  from ('192.168.86.243', 3128)". The control connects from an ephemeral port, because a control
  from the bridge's own port left a TIME_WAIT on the attack's exact address pair, which made the
  attack fail `EADDRINUSE` whatever the profile said. That errno therefore also fails the test, as
  inconclusive. The test skips if this host has no route off it.

Mutation-checked: putting back each of unfiltered `signal`, unfiltered `mach-lookup`, `/dev`
writable, no pins, no masks, the local-port outbound egress rule, no peer process-group check, no
`PT_DENY_ATTACH`, no profile cleanup, and no member sweep fails its test.

## What I found in the inherited work

Security holes in the uncommitted profile, each measured and fixed:
1. **Egress bypass to the internet.** The egress rule allowed `network-outbound` under a `local`
   filter; a jailed command bound its source port to 3128 and connected to `1.1.1.1:80`.
2. **Host processes killable.** Unfiltered `(allow signal)`: a jail killed a host `sleep` of the
   same user. Now `(target same-sandbox)`.
3. **Mach services unfiltered.** A jail read the host pasteboard with `pbpaste`. Now only
   `com.apple.system.opendirectoryd.libinfo` (user and group lookups).
4. **Escape from teardown.** A command could leave the process group that `destroy_jail`
   kills. My first fix (refusing `setsid`/`setpgid`) did not hold; see "Teardown on darwin".
5. **`/dev` writable.** A jail opened the user's terminal for writing. Now null, zero, random and
   the process's own fds only; no `file-ioctl`.

decision-0010's claims: `(import "system.sb")` was never in the code (and is not needed); its
reason for `fs_read` was false; `PT_DENY_ATTACH` gives `SIGSEGV`, not `EBUSY`; the old SPEC's
"`network-bind` must be unscoped" does not reproduce on 27.0.1. The `LOCAL_PEERTOKEN` layout was
verified against a known peer. The body is rewritten to the measurements, marking what was not
measured. `backlog decision edit` sets only status, so the body was edited by hand, as
decision-0009's was.

Smaller: lint and gates failed on the inherited code (a docstring, `create_seatbelt_jail` and the
claims not exported, private helpers public); the profile was written world-readable; the spec
cited two test files that did not exist.

## Not covered, uncertain, or for Bruk

1. **Teardown relies on `sandbox_check`**, a libSystem export with no declaration in the
   macOS SDK's headers (checked: no header under the SDK's `usr/include` names it), so Apple
   may change it without notice. It is reached through ctypes with an arm64-specific argument layout (measured
   here only), and between `run_jail` returning and `destroy_jail`, a process that left the group
   still runs (sandboxed), as a Linux one cannot once PID 1 is gone.
2. **Egress on a shared network stack.** The bridge port is fixed at 3128 on the host's stack:
   one egress jail per host at a time (measured: a second's supervisor cannot bind and
   `run_jail` raises `JailExitUnknown`), a host service on 3128 at a LAN or wildcard address is
   reachable past the proxy, and a jailed command can listen on `0.0.0.0:3128`, reachable from
   the LAN. All of this is why egress is `BEST_EFFORT`. A per-jail port, or listeners bound by
   the host and passed in so the profile needs no `network-bind`, would narrow it; both are
   design changes, not made here.
3. **The command can kill its own supervisor** on Darwin (same sandbox). The exit code is then
   reported unknown, never forged; teardown still works.
4. **Readiness dials by path on Darwin.** A link the jail swaps in between the `lstat` and the
   connect is followed; the peer check then refuses, but the embedder has dialled whatever the
   link named. Linux has no such window.
5. **`fs_read` leaks named in the claim**: names at `/`, ancestors' metadata, host processes'
   argv through `sysctl` (environment not visible), the hardware registry, user and group
   lookups.
6. **decision-0010 says `accepted`**; I found no record that Bruk accepted it. Its body has now
   changed substantially; Bruk should confirm the status.
7. **The Mach allowlist is one service**, enough for CPython, `sh` and `git`. The
   `channel_exclusivity` and `network` `ENFORCED` grades assume that service, read-only user and
   group lookups through opendirectoryd, carries nothing out of the jail; that was not probed
   beyond its use. Larger programs (Node, a CLI that uses the keychain or trust store) may need
   more services, and each addition would need its own measurement and may lower a grade.
8. **AC #2** (bh-02 running jailed on a Mac) is another repo's step and was not attempted.
9. Not measured: `LOCAL_PEERTOKEN`'s `EINVAL` after the listener is reaped; any macOS other than
   27.0.1.
10. `board-check` still reports that TASK-0061 is in progress at size 8 with no children. That
    was so before this work; I did not split a task whose work is done.
<!-- SECTION:NOTES:END -->
