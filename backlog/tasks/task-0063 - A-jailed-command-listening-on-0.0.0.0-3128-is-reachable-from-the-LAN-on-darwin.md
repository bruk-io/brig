---
id: TASK-0063
title: 'A jailed command listening on 0.0.0.0:3128 is reachable from the LAN on darwin'
status: To Do
assignee: []
created_date: '2026-11-11 17:16'
labels:
  - darwin
  - security
dependencies: []
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
