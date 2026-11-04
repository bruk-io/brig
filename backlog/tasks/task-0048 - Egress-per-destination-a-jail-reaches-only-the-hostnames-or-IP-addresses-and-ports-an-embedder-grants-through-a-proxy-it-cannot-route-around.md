---
id: TASK-0048
title: >-
  Egress per destination: a jail reaches only the hostnames or IP addresses and
  ports an embedder grants, through a proxy it cannot route around
status: Done
assignee: []
created_date: '2026-11-03T18:23:00Z'
updated_date: '2026-11-04T01:59:00Z'
labels:
  - brig
  - egress
  - size-3
  - finish-moved
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

Check `uv run just done` exited 0

(294 earlier lines omitted)
```text
[2m01:58:45.731[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m01:58:45.735[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m01:58:45.783[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m01:58:48.241[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 3.01s
[2m01:58:48.249[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m01:58:48.252[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 4.3s[39m[0m

   ┌───────────────────────────────────────────────────────────────┐
   │                                                               │
   │                                                               │
   │   [2mWebcomponents generated to:[22m                                 │
   │    site/assets/mkdocs_likec4/likec4_views.js                  │
   │                                                               │
   │   [2mSetup and usage instructions:[22m                               │
   │    [34mhttps://likec4.dev/tooling/code-generation/webcomponent/[39m   │
   │                                                               │
   │                                                               │
   └───────────────────────────────────────────────────────────────┘

uv run mkdocs build --strict
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

[31m │  ⚠  Warning from the Material for MkDocs team[0m
[31m │[0m
[31m │[0m  MkDocs 2.0, the underlying framework of Material for MkDocs,
[31m │[0m  will introduce backward-incompatible changes, including:
[31m │[0m
[31m │  × [0mAll plugins will stop working – the plugin system has been removed
[31m │  × [0mAll theme overrides will break – the theming system has been rewritten
[31m │  × [0mNo migration path exists – existing projects cannot be upgraded
[31m │  × [0mClosed contribution model – community members can't report bugs
[31m │  × [0mCurrently unlicensed – unsuitable for production use
[31m │[0m
[31m │[0m  Our full analysis:
[31m │[0m
[31m │[0m  [4mhttps://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/[0m
[0m
INFO    -  mkdocs-likec4: No projects discovered, using default root project
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/brig/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig/docs
INFO    -  Documentation built in 12.48 seconds

== architecture validate: PASS ==
[2m01:58:52.628[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m01:58:52.649[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m01:58:52.690[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m01:58:52.691[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m01:58:53.202[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m01:58:53.530[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m01:58:53.530[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 903ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Review (reviewer agent, 2026-11-04): not closed. close-task refused: the task was accepted (promoted in f1ffe56) with no acceptance criteria, and '#1 Decision recorded' was added afterwards without the finish-moved label or a note saying why. The decision itself passes review: decision-0009 answers the question (egress enforced through one route: --unshare-net kept, the supervisor bridges loopback via SCM_RIGHTS to a per-jail host-side proxy) and settles every point the description lists (policy shape, wildcards, proxy-side resolution with private-address refusal, where the proxy runs, refusal as data via egress_decisions, the grade capped by DRAFT-0028, the JSON log line). It is written as Context, Decision and Consequences, status accepted, acceptance recorded. Full check passed with no file changes. To close: whoever owns the finish line adds the finish-moved label and a note on the added criterion, commits, and close-task is run again.

Lead, 2026-11-04: finish moved by me. The draft was promoted with no criteria, and I added 'Decision recorded' in a separate edit, as record-decision asks of a design task; the label and this note were missed then.

Review (reviewer agent, 2026-11-04): closed. decision-0009 answers the question (egress enforced through one route: --unshare-net kept, the supervisor bridges loopback via SCM_RIGHTS to a per-jail host-side proxy) and settles every point the description lists. Written as Context, Decision and Consequences, status accepted, acceptance by @bruk recorded. Full check passed with no file changes. The earlier refusal (criterion added after promotion) is answered by the finish-moved label and the coordinator's note. No findings filed.
<!-- SECTION:NOTES:END -->
