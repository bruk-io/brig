---
id: TASK-0063
title: 'A jailed command listening on 0.0.0.0:3128 is reachable from the LAN on darwin'
status: In Progress
assignee: []
created_date: '2026-11-11 17:16'
updated_date: '2026-11-12 03:51'
labels:
  - darwin
  - security
dependencies: []
modified_files:
  - src/brig/infra/sockets.py
  - src/brig/infra/supervisor/wire.py
  - src/brig/infra/supervisor/program.py
  - src/brig/infra/supervisor/link.py
  - src/brig/domain/jail_types/seatbelt.py
  - src/brig/presentation/drivers/seatbelt.py
  - docs/spec/index.md
type: bug
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0061's pre-merge review (2026-11-11). On darwin, egress uses a fixed bridge port, 3128, on the host's shared network stack. A jailed command can listen on 0.0.0.0:3128, so a machine on the person's LAN can reach it, and a host service on 3128 at another local address is reachable past the proxy. It is also why only one egress jail can run per host. A per-jail port was planned in TASK-0061 but not built. Bruk is deciding whether to give each jail its own port.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A jailed command on darwin cannot accept connections from off the host
- [ ] #2 Two egress jails can run at once on one Mac
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Direction: each darwin egress jail gets its own bridge port instead of the fixed 3128. The orchestrator chose this on Bruk's behalf (recommended in TASK-0061's review); Bruk has not confirmed it, and any decision recorded here says so.

Measured before planning (macOS 27.0.1, scratch probes):
- A jailed process accepts on listeners the host bound and passed in as fds, with no network-bind and no network-inbound in its profile: both 127.0.0.1:P and [::1]:P bridged. With only (allow network-outbound (remote tcp "localhost:P")), every bind in the jail is EPERM, 0.0.0.0:P included. With the current (allow network-bind network-inbound (local tcp "localhost:P")), a jailed process bound and listened on 0.0.0.0:P.
- A host wildcard reservation on P refuses a third party's plain bind of LAN:P (EADDRINUSE), but not one with SO_REUSEADDR or SO_REUSEPORT; SBPL takes only localhost or * as a host, and localhost matches every local address. So a host program that binds the jail's own port on another local address, with reuse options, stays reachable past the proxy: item 3 cannot be delivered in full, and no reservation is added for the part it could.

### Order of work
1. Infra (src/brig/infra/sockets.py): bridge_listeners() binds 127.0.0.1:0 and [::1] at the same port, listening, and returns the port and both sockets.
2. Infra (src/brig/infra/supervisor/wire.py, program.py, link.py): link.Bridge carries host-bound listeners, passed as fixed fds; the exec request says so; program.py accepts on them instead of binding, closes them in the command and the freezer. bwrap's path (the supervisor binding 3128 in the jail's own network namespace) is unchanged.
3. Domain (src/brig/domain/jail_types/seatbelt.py): the egress rule is outbound only, to remote localhost at the jail's port; the egress claim text and ceilings re-graded from measurement.
4. Presentation (src/brig/presentation/drivers/seatbelt.py): bind the listeners per jail, compile with that port, set the proxy variables to it, close the sockets on every failure path.
5. Tests: unit (profile has no bind or inbound rule), e2e: two egress jails at once; a jailed command cannot listen on its bridge port or any other (unjailed control; fails with the old rule); a host service at another local address on the jail's port (pins the residual); the existing egress batteries.
6. decision-0010 item 4, the spec, the C4 model; a decision record for the per-jail port as the orchestrator's choice.
7. uv run just done and uv run just test-e2e; push egress-port, draft PR, Linux CI green; no freezer left.

### Risks
- Shared infra (wire, program, link) runs on Linux: the bwrap path must stay byte-for-byte in behaviour; Linux CI is the check.
- Listener fds leaking into the command or the freezer would let them accept: both are closed there, and a test reads the command's open fds.
- Socket lifetime across a failed create: sockets are owned by the Bridge and closed idempotently.

### Proof
- The new e2e tests fail with the old egress rule restored, and the concurrency test fails with a fixed port.
- just done, just test-e2e and Linux CI green; ps -axo pid,command | grep -i freez empty.
<!-- SECTION:PLAN:END -->
