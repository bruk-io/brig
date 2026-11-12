---
id: DRAFT-0036
title: >-
  Darwin egress residual is wider than graded: plain binds and link-local reach
  the jail's port
status: Draft
assignee: []
created_date: '2026-11-12 08:33'
updated_date: '2026-11-12 13:19'
labels:
  - darwin
  - security
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0063's review (2026-11-12, macOS 27). The egress claim (domain/jail_types/seatbelt.py SEATBELT_NETWORK_EGRESS_CLAIM and ceilings docstring), spec index.md line 248 and decision-0011 say a host program reaches past the proxy only if it binds the jail's port on another local address WITH an address-reuse option. Measured: while bridge_listeners holds 127.0.0.1:P and [::1]:P, a plain bind (no reuse option) of 192.168.86.243:P, fe80::1%lo0:P and fe80::<en1>%en1:P all succeed, and a jailed connect to localhost:P reaches the LAN address and both link-local addresses (127.0.0.2 and off-host are EPERM). Repro: uv run python -c 'from brig.infra.sockets import bridge_listeners; ...' then a plain socket.bind((LAN,P)). Cheap narrowing measured: the host binding P without reuse on each local address present at create (bound, NOT listening) refuses every specific squatter bind with or without SO_REUSEADDR/SO_REUSEPORT (EADDRINUSE), and a connect to LAN:P then does not reach a wildcard SO_REUSEADDR squatter (timed out). It leaves addresses that appear after create (DHCP, VPN utun) open.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The claim, ceilings docstring, spec and decision-0011 state the residual as measured: any bind of the port at a non-loopback local address, link-local included, reuse option or not
- [ ] #2 Either the host reserves the jail's port, bound and not listening, on every local address at create, with an e2e test that a squatter at the LAN address is refused, or a decision records why not
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Covered by commit 9068f9a on egress-port (PR #2), under TASK-0063, and archived rather than promoted: the work is done in that task, and a reviewer judges it there.

- AC #1: the claim (SEATBELT_NETWORK_EGRESS_CLAIM), the ceilings docstring, docs/spec/index.md, decision-0011 (new item 4) and decision-0010 item 4 now state the measured residual. Before the fix, any bind of the port at a non-loopback local address, link-local included, reuse option or not. After it, only an address that appears after create.
- AC #2: the host reserves the jail's port, bound and not listening, on every local address present at create (infra.sockets.bridge_listeners, held on the Jail until destroy). test_a_host_program_cannot_take_the_jails_port_at_another_local_address shows plain, SO_REUSEADDR and SO_REUSEPORT squatters at the LAN address and at fe80::1%lo0 refused with EADDRINUSE, and a wildcard squatter not reached. Its unjailed control (only the loopbacks held) binds every one, and the test fails with the reservations removed.
<!-- SECTION:NOTES:END -->
