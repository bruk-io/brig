---
id: TASK-0049
title: >-
  The egress route bounds neither its connections nor a handshake's whole time:
  a jailed program can hold host threads and fds without limit
status: To Do
assignee: []
created_date: '2026-11-04T02:59:00Z'
updated_date: '2026-11-04T12:40:00Z'
labels:
  - brig
  - egress
  - size-3
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Review of TASK-0001.36. infra/proxy/program.py starts one daemon thread per connection (two once relaying) with no cap, and the supervisor's bridge (infra/supervisor/program.py _accept/_bridge_one) does the same in PID 1. _HANDSHAKE_TIMEOUT_S is set with settimeout, so it limits each recv, not the whole handshake: a client that sends one byte every 29 s keeps its _http head read going until _HEAD_LIMIT (64 KiB), about three weeks. A program in the jail can open connections to 127.0.0.1:3128 until the host-side proxy, a child of the embedder, runs out of threads or fds. destroy_jail still ends it (KILL of the proxy's group), so law 7 holds; the cost is to the host while the jail runs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A handshake that has not named its destination within a fixed total time is closed, proven by an e2e test with a slow client
- [ ] #2 The proxy and the bridge each hold at most a stated number of connections at once; one more is refused and closed, proven by an e2e test that counts the proxy's threads and fds
- [ ] #3 The proxy and the supervisor's bridge each cap concurrent connections per jail at a named constant, and a connection past the cap is refused (403 or SOCKS 0x01 for the proxy, closed for the bridge); e2e
- [ ] #4 A handshake has a total deadline, not a per-read one, a named constant; e2e: a client sending one header byte per second is closed past the total limit, with the limit lowered in the test so it runs in seconds
- [ ] #5 The docstrings and spec state both limits; destroy_jail still ends everything (law 7)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
