---
id: TASK-0061
title: A Seatbelt jail for darwin
status: In Progress
assignee: []
created_date: '2026-11-10 17:16'
updated_date: '2026-11-11 15:07'
labels:
  - darwin
  - security
  - size-8
dependencies: []
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
Taken over 2026-11-11 from an agent that ran out of quota. Everything inherited (decision-0010, infra Darwin support, the uncommitted seatbelt jail type and driver) is treated as unreviewed; claims are re-measured on this Mac (macOS 27.0.1, /usr/bin/sandbox-exec).

Measured before planning (scratch probes, to be pinned by e2e tests):
- The profile does not import system.sb, and Python, sh and git start without it; /etc/passwd and /usr/lib/dyld are then unreadable. decision-0010's reason for fs_read BEST_EFFORT (system.sb's grants) is false; the real reasons are the listing of / and ancestor metadata.
- Unfiltered (allow signal) lets a jail SIGTERM any host process of the user (killed a host sleep). (allow signal (target same-sandbox)) refuses it and still lets a jail signal its own children.
- Unfiltered (allow mach-lookup) lets a jail read the host pasteboard (pbpaste). With mach-lookup limited to com.apple.system.opendirectoryd.libinfo, pbpaste is refused and pwd/grp/whoami/git/ssl/subprocess still work.
- (deny syscall-unix (syscall-number SYS_setsid SYS_setpgid)) refuses both, so a command cannot leave the jail's process group and outlive destroy_jail's group kill.
- LOCAL_PEERTOKEN (0x006, 32 bytes) layout verified against a forked listener: pid at [5], pidversion at [7] equals proc_pidinfo's p_idversion; pbi_pgid equals os.getpgid.
- PT_DENY_ATTACH: a child calling ptrace(PT_ATTACHEXC, ppid) is killed with SIGSEGV; without it, attach and task_for_pid already fail (EPERM, KERN_FAILURE).
- Unix sockets: bind and connect allowed in the channel directory with a subpath-filtered network-bind; connect to a host socket in a readable root and bind outside are EPERM; TCP, UDP and DNS are refused.
- (remote tcp "localhost:P") also matches [::1]:P and the LAN address at P, not other ports.

Steps:
1. Domain (seatbelt.py): narrow the header (signal same-sandbox, mach-lookup libinfo only, deny setsid/setpgid, /dev and ioctl narrowed as far as startup allows, / metadata only if startup allows); _render_atom private; claims' text corrected to the measured reasons.
2. Egress on a shared network stack: per-jail bridge port chosen on the host (fails closed if taken), and on darwin the supervisor's [::1] bind is required rather than best-effort, since the profile's localhost filter reaches [::1].
3. Presentation: export create_seatbelt_jail and the seatbelt claims from brig; lint fix for the Raises section.
4. Tests: unit (compile order, render, escaping, ceilings), integration (driver with fakes where bwrap has them), e2e on darwin with an unjailed control beside every attack: write outside the project, network egress, masked secret read, another jail's channel, host process signal, pasteboard, setsid escape, pin rename, channel readiness with a verified peer, interrupt and destroy, report battery held with at_most.
5. Correct decision-0010's unmeasured or false claims; update docs/spec where it repeats them.
6. uv run just done and uv run just test-e2e green on this Mac; report in implementation notes and .gemini-report.md.
<!-- SECTION:PLAN:END -->
