---
id: TASK-0063
title: 'A jailed command listening on 0.0.0.0:3128 is reachable from the LAN on darwin'
status: In Progress
assignee: []
created_date: '2026-11-11 17:16'
updated_date: '2026-11-12 08:34'
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
- [x] #1 A jailed command on darwin cannot accept connections from off the host
- [x] #2 Two egress jails can run at once on one Mac
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Report (2026-11-12), measured on macOS 27.0.1 with /usr/bin/sandbox-exec. Draft PR bruk-io/brig#2; left In Progress for a reviewer. Per-jail ports were the orchestrator's choice on Bruk's behalf; decision-0011 records that and stays proposed until Bruk confirms.

## Commits
- bbc97d3 feat(seatbelt): a bridge port per egress jail, bound by the host, so the jail binds nothing
- 3e77bd9 and the notes commit after it: plan and report, written by the backlog CLI

## Results
- uv run just done: exit 0, all steps pass. Unit 418 passed; integration 100 passed and 2 skipped in each pass; e2e 132 passed and 118 skipped.
- uv run just test-e2e: exit 0, 132 passed, 118 skipped, 0 failed. No seatbelt test skips.
- ps -axo pid,command | grep -i freez: nothing. ~/.brig: no leftovers.
- Linux CI on PR #2: green (run 43164505840).

## What changed
- The host binds 127.0.0.1 at a port the kernel picks and [::1] at the same port, with no address-reuse option (infra.sockets.bridge_listeners).
- Both listeners go to the supervisor as fds 6 and 7 (wire.BRIDGE_LISTENER_FDS; bridge_inherited in the exec request). The supervisor marks them close-on-exec before starting anything, then accepts on them.
- The profile's one egress rule is (allow network-outbound (remote tcp "localhost:<port>")).
- bwrap's path (binding 3128 in the jail's own network namespace) is unchanged; Linux requests carry bridge_inherited false.

## Measured
- A jailed process accepts on listeners passed in, with no network-bind or network-inbound rule.
- With only the outbound rule, every bind in the jail is EPERM, 0.0.0.0:<port> included.
- With the TASK-0061 rule (bind and inbound on the local port), a jailed command listened on 0.0.0.0:<port>.
- A host wildcard reservation on the port refuses a third party's plain bind of LAN:<port> but not one with SO_REUSEADDR or SO_REUSEPORT. It was rejected, since most servers set those options.

## Done means
1. Two egress jails at once: test_two_jails_with_egress_run_at_once. With a fixed port it fails; the second jail's start raised JailSpawnFailed.
2. No connection from off the host: test_a_jailed_command_cannot_listen_for_a_connection_from_off_the_host. It tries the wildcard at the jail's port (with each reuse option), the LAN address there, and any port. All four are EPERM; unjailed, the same program listens. With the old rule restored the test fails. test_the_command_holds_none_of_the_bridge_s_listeners fails without the close-on-exec: the command held fds 6 and 7.
3. Host service at another local address on the jail's port: cannot be delivered. SBPL takes only localhost or * as the host, and localhost matches every local address. test_a_host_program_on_the_jails_port_at_another_address_is_reached_past_the_proxy pins that a squatter at the LAN address with SO_REUSEADDR is reached. What is narrower than before: the port is the jail's own, picked by the kernel at create, so only a host program that binds that one port after the jail starts is reached. It is no longer any service on a well-known port (3128 is a common proxy port).
4. Re-grade: network with egress stays BEST_EFFORT. Two of its three reasons are gone (LAN reach to the command; one egress jail per host), each shown above. The third (item 3) holds until the host binds the jail's port, which is BEST_EFFORT as decision-0008 defines it. Every other grade is unchanged.
5. decision-0010 item 4 and the egress bullet in item 1, the spec (the seatbelt paragraph and the supervisor/proxy paragraph), and the C4 sockets and supervisor-link components plus the seatbeltDriver to sockets relationship are updated. decision-0011 is new.

## Open
- decision-0011 needs Bruk's confirmation.
- The residual in item 3.

Check `uv run just done` exited 0

(473 earlier lines omitted)
```text
[2m07:11:26.408[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m07:11:26.409[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m07:11:26.409[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m07:11:26.410[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m07:11:26.416[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m07:11:26.670[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 268ms
[2m07:11:26.673[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/src/github.com/bruk-io/brig/.claude/worktrees/egress-port/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m07:11:26.673[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 554ms[39m[0m

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
INFO    -  Building documentation to directory: /Users/brukhabtu/src/github.com/bruk-io/brig/.claude/worktrees/egress-port/site
INFO    -  mkdocs-likec4: Generating web component for default project from /Users/brukhabtu/src/github.com/bruk-io/brig/.claude/worktrees/egress-port/docs
INFO    -  Documentation built in 1.96 seconds

== architecture validate: PASS ==
[2m07:11:27.499[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m07:11:27.503[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/src/github.com/bruk-io/brig/.claude/worktrees/egress-port/docs/architecture[0m
[2m07:11:27.510[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m07:11:27.510[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m07:11:27.643[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 41 source files[0m
[2m07:11:27.770[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (41 files)[22m[0m
[2m07:11:27.770[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 271ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 35 elements, 85 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

No repro: as a recorded failing run. The fix is on this branch, and a reviewer can't check out the pre-fix code here. The reviewer showed the failure in memory instead: with render_profile patched to add back the TASK-0061 rule (allow network-bind network-inbound (local tcp "localhost:P")), test_a_jailed_command_cannot_listen_for_a_connection_from_off_the_host fails, and the jail listens on 0.0.0.0:P and 192.168.86.243:P. On this branch it passes.
<!-- SECTION:NOTES:END -->
