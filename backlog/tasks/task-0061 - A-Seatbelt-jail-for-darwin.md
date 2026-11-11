---
id: TASK-0061
title: A Seatbelt jail for darwin
status: In Progress
assignee: []
created_date: '2026-11-10 17:16'
updated_date: '2026-11-11 15:32'
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
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Report of the second worker (2026-11-11), measured on macOS 27.0.1 with /usr/bin/sandbox-exec. Not pushed; left In Progress for a reviewer. AC #1 is ready for review; AC #2 is bh-02's and was not attempted.

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

## Results on this Mac

- `uv run just done`: exit 0, "done: all steps passed". Lint, typecheck and gates pass;
  pypeeker rule tests 51 passed; unit 417 passed; integration 93 passed and 2 skipped, both
  passes; e2e 116 passed and 118 skipped; docs, architecture validate and architecture lint pass.
- `uv run just test-e2e`: exit 0, 116 passed, 118 skipped, 0 failed. The 118 skips are the same
  Linux-only tests as before this work (bwrap, procfs, `SO_PEERCRED`, root); no seatbelt test
  skips here. Before this work it was 86 passed, 118 skipped.
- Linux CI was not run (no push). The shared code changed for Linux is limited: the supervisor's
  `[::1]` bind failure propagates only when `sys.platform == "darwin"`. The new integration tests
  start nothing and should run on Linux; the new e2e files skip there.

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
directory refused, interrupt delivered, timeout, cwd, teardown with an orphan that tried to
`setsid`, no supervisor fd in the command, ptrace of the supervisor kills the command
(`test_seatbelt_journey.py`, `test_seatbelt_channels.py`, `test_seatbelt_supervisor.py`).

Mutation-checked: putting back each of unfiltered `signal`, unfiltered `mach-lookup`, the missing
`setsid`/`setpgid` deny, `/dev` writable, no pins, no masks, the local-port outbound egress rule,
no peer process-group check, no `PT_DENY_ATTACH`, and no profile cleanup each fails its test.

## What I found in the inherited work

Security holes in the uncommitted profile, each measured and fixed:
1. **Egress bypass to the internet.** The egress rule allowed `network-outbound` under a `local`
   filter; a jailed command bound its source port to 3128 and connected to `1.1.1.1:80`.
2. **Host processes killable.** Unfiltered `(allow signal)`: a jail killed a host `sleep` of the
   same user. Now `(target same-sandbox)`.
3. **Mach services unfiltered.** A jail read the host pasteboard with `pbpaste`. Now only
   `com.apple.system.opendirectoryd.libinfo` (user and group lookups).
4. **Escape from teardown.** A command could `setsid` out of the process group that
   `destroy_jail` kills. Now `setsid`/`setpgid` are refused.
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

1. **Refusing `setsid`/`setpgid` is a compatibility cost I chose for teardown's sake.** A
   command that daemonises or asks for a new session fails in a Seatbelt jail. Without it, a
   jailed process can outlive `destroy_jail` (still sandboxed). Bruk may want to confirm this
   trade, since it may matter for what bh-02 runs (AC #2).
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
   argv through `sysctl` (environment not visible), user and group lookups.
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
