---
id: TASK-0049
title: >-
  The egress route bounds neither its connections nor a handshake's whole time:
  a jailed program can hold host threads and fds without limit
status: In Progress
assignee: []
created_date: '2026-11-04T02:59:00Z'
updated_date: '2026-11-04T13:29:00Z'
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
- [x] #1 A handshake that has not named its destination within a fixed total time is closed, proven by an e2e test with a slow client
- [ ] #2 The proxy and the bridge each hold at most a stated number of connections at once; one more is refused and closed, proven by an e2e test that counts the proxy's threads and fds
- [ ] #3 The proxy and the supervisor's bridge each cap concurrent connections per jail at a named constant, and a connection past the cap is refused (403 or SOCKS 0x01 for the proxy, closed for the bridge); e2e
- [ ] #4 A handshake has a total deadline, not a per-read one, a named constant; e2e: a client sending one header byte per second is closed past the total limit, with the limit lowered in the test so it runs in seconds
- [ ] #5 The docstrings and spec state both limits; destroy_jail still ends everything (law 7)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

Repro at 58ad7bd98517, test files: tests/e2e/test_egress_handshake_deadline.py; command: `uv run pytest tests/e2e/test_egress_handshake_deadline.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
_ test_a_client_sending_one_header_byte_a_second_is_closed_past_the_total_limit _

    def test_a_client_sending_one_header_byte_a_second_is_closed_past_the_total_limit() -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as streams:
            out = Path(streams) / "out.json"
            jail = create_bwrap_jail(
                (sys.executable, "-I", "-c", _CLIENT, str(_HORIZON_S)),
                egress=EgressPolicy((Destination("granted.test", 80),)),
                egress_limits=EgressLimits(handshake_s=_LIMIT_S),
                stdio=Stdio(stdout=str(out)),
            )
            try:
                assert run_jail(jail, timeout_s=60) == 0
            finally:
                destroy_jail(jail)
            seen = json.loads(out.read_text())
    
        closed_after = seen["closed_after"]
>       assert closed_after is not None, "the slow handshake was still open past the total limit"
E       AssertionError: the slow handshake was still open past the total limit
E       assert None is not None

tests/e2e/test_egress_handshake_deadline.py:76: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_egress_handshake_deadline.py::test_a_client_sending_one_header_byte_a_second_is_closed_past_the_total_limit
1 failed in 8.37s
```

Check `uv run just done` exited 0

(332 earlier lines omitted)
```text
[2m13:25:30.438[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m13:25:30.449[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m13:25:30.452[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m13:25:32.587[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.24s
[2m13:25:32.590[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m13:25:32.593[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig-pins/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-pins/docs
INFO    -  Documentation built in 5.47 seconds

== architecture validate: PASS ==
[2m13:25:37.367[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m13:25:37.384[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m13:25:37.409[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m13:25:37.410[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m13:25:37.847[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m13:25:38.136[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m13:25:38.136[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 770ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Worker, 2026-11-04 (branch claude/egress-bounds): commits c63cd3d (the handshake limit lowerable on the proxy's config line, still per read), 58ad7bd (the repro, tests/e2e/test_egress_handshake_deadline.py, recorded failing above: closed_after was None at 8 s with the limit at 2 s), bada963 (the fix, its tests and docs).

What changed:
- Proxy (infra/proxy/program.py): CONNECTION_LIMIT = 256 connections served at once. One more gets no thread: _Capped holds it in _main's own select loop until its first byte (at most as many again, each for at most the handshake deadline; past that it is closed unanswered), then _refuse answers 403 (body 'brig: egress refused: the jail holds as many connections as it may') or a SOCKS5 method choice plus reply 0x01, and closes it. It makes no decision line, since it named no destination. HANDSHAKE_DEADLINE_S = 30 s is now a total: _recv sets each handshake read's timeout to what is left of the deadline taken at arrival. A thread that cannot start gives its slot back instead of ending the proxy.
- Bridge (infra/supervisor/program.py): at most wire.BRIDGE_CONNECTION_LIMIT = 256 relayed at once, one BoundedSemaphore across both listeners; one more is accepted and closed at once, never handed to the proxy.
- How a test lowers them: EgressLimits(connections, bridge_connections, handshake_s) on create_bwrap_jail. Each field defaults to its program's constant, and check_egress_limits refuses one that is not above zero or is above that default (PolicyEgressLimitOutOfRange), so a limit can be lowered and never raised. Each value travels on the host's own line to its program: the proxy's config line (connections, handshake_s) and the supervisor's exec request (bridge_limit). Both are closed JSON shapes the host writes on fds the command never holds. argv was not used for three reasons. The supervisor's argv is readable in the jail as /proc/1/cmdline. The proxy's argv (python -I -) is how the host and the batteries find it. And neither program parses arguments.
- Docs: the spec's infra section (the limits, and why the lines and not argv), its presentation section and law 7's held-by list; a glossary entry 'egress limits'; and the docstrings of both programs, wire, launch, link, EgressLimits and create_bwrap_jail.
- Tests: tests/e2e/test_egress_connection_caps.py. With the proxy's cap at 3, the proxy serves 3 tunnels, refuses one more with 403 and SOCKS 0x01, and its count on the host is +2 threads and +2 fds per tunnel, unchanged by the refusals. With the bridge's cap at 3, one more is closed unanswered, the proxy's count does not move, and PID 1's threads, counted in the jail, do not move either. In both, closing a tunnel frees a slot. destroy_jail with the route full leaves no proxy, thread or fd (law 7). tests/integration/test_egress_create_refusal.py checks the refusal of a raised or zero limit. The repro now passes. The new e2e files passed 8 runs in a row.
- Not bounded, and stated: after the proxy closes a connection, the bridge's relay for it lasts until the client in the jail sends or closes. That relay is bounded by the bridge's cap only, and costs the jail's own PID 1, not the proxy.

just done passed (record above). Criteria left unticked for the reviewer.

Check `uv run just done` exited 0

(331 earlier lines omitted)
```text
[2m13:28:57.619[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m13:28:57.686[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m13:28:57.827[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m13:29:02.161[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 4.71s
[2m13:29:02.164[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m13:29:02.166[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 6.9s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig-pins/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-pins/docs
INFO    -  Documentation built in 10.44 seconds

== architecture validate: PASS ==
[2m13:29:04.019[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m13:29:04.050[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m13:29:04.139[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m13:29:04.140[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m13:29:05.075[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m13:29:05.504[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m13:29:05.504[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.4s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
