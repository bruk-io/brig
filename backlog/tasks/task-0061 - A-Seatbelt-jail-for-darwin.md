---
id: TASK-0061
title: A Seatbelt jail for darwin
status: In Progress
assignee: []
created_date: '2026-11-10 17:16'
updated_date: '2026-11-10 20:06'
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
1. Record design rulings in decision-0010 (SBPL compilation of FsPolicy/EgressPolicy, PT_DENY_ATTACH supervisor protection, LOCAL_PEERTOKEN + proc_pidinfo channel readiness, measured Seatbelt grade ceilings).
2. Update docs/spec/index.md and docs/architecture/ C4 models (seatbelt-jail-type, seatbelt-driver, _relationships, components view) first; verify just arch-validate, just arch-lint, and just docs.
3. Add Darwin support to brig.infra (placeholders xattr + proc_pidinfo start_time, sockets O_RDONLY/F_GETPATH/LOCAL_PEERTOKEN/proc_pidinfo, supervisor PT_DENY_ATTACH, proxy SOCK_STREAM fallback + getifaddrs host addresses) so all existing unit, integration, and platform-applicable e2e tests pass on macOS.
4. Implement brig.domain.jail_types.seatbelt (Python 3.15 Template-rendered SBPL compiler, rules, pins, placeholders_for, writable_shared_paths, ceilings, seatbelt_argv) and brig.presentation.drivers.seatbelt (create_seatbelt_jail), re-exported from brig.
5. Write unit, integration, and e2e test batteries on Darwin (test_seatbelt_compile, test_seatbelt_ceilings, test_seatbelt_driver, test_seatbelt_journey, test_seatbelt_fs_policy_battery, test_seatbelt_supervisor_isolation_battery, test_seatbelt_channel_readiness_battery, test_seatbelt_egress_battery, test_seatbelt_report_battery).
6. Run uv run just done and uv run just test-e2e until green; record implementation notes on TASK-0061 and write .gemini-report.md and .gemini-done.
<!-- SECTION:PLAN:END -->
