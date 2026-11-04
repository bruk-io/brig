---
id: TASK-0048
title: >-
  Egress per destination: a jail reaches only the hostnames or IP addresses and
  ports an embedder grants, through a proxy it cannot route around
status: To Do
assignee: []
created_date: '2026-11-03T18:23:00Z'
updated_date: '2026-11-04T01:55:00Z'
labels:
  - brig
  - egress
  - size-3
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Egress-is-enforced-through-one-route-the-jail-keeps-only-loopback-the-supervisor-bridges-it-to-a-host-side-proxy-that-allows-granted-hostnames-and-IP-addresses-per-port.md
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder (bh-02, DRAFT-0026 on its board) wants network grants per hostname and/or IP address plus port, approved once or always by its person. Today a bwrap jail has no network (--unshare-net) or the whole host's. TASK-0001's criterion 5 keeps egress through the allowlisting proxy, and its open question asks whether egress is cooperative or enforced; per-destination grants need it enforced: the jail's only route out is a channel the supervisor relays to a host-side proxy, which allows CONNECT host:port (or TLS SNI) and raw TCP to IP:port against the policy's allowlist, so a program that ignores HTTPS_PROXY reaches nothing. To settle in a decision: the policy shape (EgressPolicy of host and IP entries with ports, wildcards or not, whether a granted hostname covers its resolved addresses), where the proxy runs (the supervisor or a library thread), how a refusal reaches the embedder so it can ask its person, the grade (network ENFORCED for the proxy route, still capped by DRAFT-0028's host-socket gap), and the JSON log line each decision writes (criterion 15).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decision recorded
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: decision-0009 written (proposed), under TASK-0001 (criterion 5 and its egress open question). Once accepted it answers that question (enforced, through the supervisor's bridge to a host-side proxy) and the network half of the embedder's capability-grants intent. Awaiting the owner's acceptance.

Decision accepted by @bruk, 2026-11-04 (decision-0009, status accepted). Build tasks follow under TASK-0001.
<!-- SECTION:NOTES:END -->
