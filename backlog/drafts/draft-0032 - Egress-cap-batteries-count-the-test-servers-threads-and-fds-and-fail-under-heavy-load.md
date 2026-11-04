---
id: DRAFT-0032
title: >-
  Egress cap batteries count the test server's threads and fds, and fail under
  heavy load
status: Draft
assignee: []
created_date: '2026-11-04T15:17:00Z'
labels:
  - brig
  - tests
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen by TASK-0053's worker, 2026-11-04, under a load heavier than the full tier (the e2e layer in a loop plus 4-6 CPU busy-loops): test_egress_connection_caps.py::test_the_proxy_serves_at_most_its_cap_and_refuses_one_more_with_403_or_socks_0x01 failed 3 times on the fd count (assert 12 == (7 + (2 * 3))), and test_destroy_jail_at_the_cap_leaves_no_proxy_process_thread_or_fd failed twice with an extra process_request_thread, which is the test's own HTTP server's thread, not the proxy's. The batteries should count only the proxy's threads and fds (by its pid), or wait for the server's threads to finish, so a leak in brig is what fails them.
<!-- SECTION:DESCRIPTION:END -->
