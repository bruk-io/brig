---
id: TASK-0054
title: >-
  An egress decision refused for a private address names the address the name
  resolved to
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T20:22:00Z'
updated_date: '2026-11-04T20:23:00Z'
labels:
  - size-1
  - egress
dependencies: []
modified_files:
  - src/brig/domain/policy/egress_record.py
  - src/brig/infra/proxy/program.py
  - src/brig/presentation/jail.py
  - tests/e2e/test_egress_live_battery.py
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder that turns a refusal into a prompt can't offer the one grant that would allow a name pointing at a private address: decision-0009's rule is that only an IP-literal grant of that address opens it, and `EgressDecision` carries the name and port but not the address (`PrivateAddress.address` is dropped in `_judge`). An embedder asking its person needs the address to offer that IP-literal grant, with a warning that it is private.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A private-address refusal's decision line and `EgressDecision.address` name the address the name resolved to; every other decision's is ''
- [ ] #2 A real-jail test: a name granted by host, resolving to 127.0.0.1 with no IP-literal grant, is refused with reason private-address and address 127.0.0.1
- [ ] #3 just done passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Thread the address through the one path a decision takes: `_judge` passes `str(outcome.address)` for a `PrivateAddress` ('' otherwise) to `_Decisions.record`, which writes it as an `address` field after `reason`; `presentation.jail._decision` reads it (a str, required) into a new `EgressDecision.address`.

### Order of work
1. `EgressDecision.address` and its docstring; `_DecisionFields` and `record`; `_judge`; `_decision`.
2. The live battery's field-order assertion gains `address` ('' for each of its decisions).
3. A real-jail test: `near.test` granted by name, `egress_hosts` mapping it to 127.0.0.1, no IP-literal grant; one CONNECT through the proxy is refused, and its decision reads reason private-address, address 127.0.0.1.

### Risks
- A decision line without the field is dropped like an unreadable one (no backwards compatibility: the proxy and the reader ship together).

### Proof
The new real-jail test fails before the change (no `address`); `just done` passes.
<!-- SECTION:PLAN:END -->
