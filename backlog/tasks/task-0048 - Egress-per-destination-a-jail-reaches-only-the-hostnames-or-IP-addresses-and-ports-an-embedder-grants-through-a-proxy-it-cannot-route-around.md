---
id: TASK-0048
title: >-
  Egress per destination: a jail reaches only the hostnames or IP addresses and
  ports an embedder grants, through a proxy it cannot route around
status: To Do
assignee: []
created_date: '2026-11-03T18:23:00Z'
labels:
  - brig
  - egress
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder (bh-02, DRAFT-0026 on its board) wants network grants per hostname and/or IP address plus port, approved once or always by its person. Today a bwrap jail has no network (--unshare-net) or the whole host's. TASK-0001's criterion 5 keeps egress through the allowlisting proxy, and its open question asks whether egress is cooperative or enforced; per-destination grants need it enforced: the jail's only route out is a channel the supervisor relays to a host-side proxy, which allows CONNECT host:port (or TLS SNI) and raw TCP to IP:port against the policy's allowlist, so a program that ignores HTTPS_PROXY reaches nothing. To settle in a decision: the policy shape (EgressPolicy of host and IP entries with ports, wildcards or not, whether a granted hostname covers its resolved addresses), where the proxy runs (the supervisor or a library thread), how a refusal reaches the embedder so it can ask its person, the grade (network ENFORCED for the proxy route, still capped by DRAFT-0028's host-socket gap), and the JSON log line each decision writes (criterion 15).
<!-- SECTION:DESCRIPTION:END -->
