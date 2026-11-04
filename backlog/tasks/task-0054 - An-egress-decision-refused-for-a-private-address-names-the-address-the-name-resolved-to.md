---
id: TASK-0054
title: >-
  An egress decision refused for a private address names the address the name
  resolved to
status: To Do
assignee: []
created_date: '2026-11-04T20:22:00Z'
labels:
  - size-1
  - egress
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder that turns a refusal into a prompt can't offer the one grant that would allow a name pointing at a private address: decision-0009's rule is that only an IP-literal grant of that address opens it, and `EgressDecision` carries the name and port but not the address (`PrivateAddress.address` is dropped in `_judge`). An embedder's TASK of its own needs it to offer an IP-literal grant with a warning.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A private-address refusal's decision line and `EgressDecision.address` name the address the name resolved to; every other decision's is ''
- [ ] #2 A real-jail test: a name granted by host, resolving to 127.0.0.1 with no IP-literal grant, is refused with reason private-address and address 127.0.0.1
- [ ] #3 just done passes
<!-- AC:END -->
