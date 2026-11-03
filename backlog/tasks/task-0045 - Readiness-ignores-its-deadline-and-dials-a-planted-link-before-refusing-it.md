---
id: TASK-0045
title: Readiness ignores its deadline and dials a planted link before refusing it
status: In Progress
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:51:00Z'
labels:
  - brig
  - channels
  - size-3
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (both demonstrated): (a) a jail that calls listen(0) and fills its own backlog makes await_channel_ready(timeout_s=2) block for 10 s (the blocking connect in infra/sockets.py ignores the deadline; law 7). (b) a link planted at the reserved name is dialled as the embedder before PEER_OUTSIDE_JAIL refuses it, so a socket-activated host service is triggered. Proposed: hold the channel directory's fd from creation; openat(dirfd, name, O_PATH|O_NOFOLLOW), require S_ISSOCK, connect non-blocking to /proc/self/fd/N with a poll deadline (the reviewer checked both work).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 await_channel_ready honours timeout_s against a jail that fills its own listen backlog and never accepts: it returns ChannelNotReady (or a terminal outcome) within the deadline plus a small bound; e2e recorded failing before the fix
- [ ] #2 A link planted at the reserved name is refused without the embedder connecting to what it names: brig opens the name beneath a directory fd it holds from creation with O_PATH|O_NOFOLLOW, requires a socket, and connects through that fd non-blocking with a poll deadline; e2e shows a host listener behind the link sees no connection; recorded failing before the fix
- [ ] #3 The returned connection is still the verified one (TASK-0001.34) and the readiness battery still passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).

Repro at 7e437873fcfd, test files: tests/e2e/test_channel_readiness_dial.py; command: `uv run pytest tests/e2e/test_channel_readiness_dial.py -q` exited 1

(16 earlier lines omitted)
```text
            daemon=True,
        )
        started = time.monotonic()
        try:
            waiter.start()
            waiter.join(_DEADLINE_S + _BOUND_S)
            elapsed = time.monotonic() - started
            finished = not waiter.is_alive()
        finally:
            destroy_jail(jail, directories=directories)
            waiter.join(10.0)
            for outcome in outcomes:
                if isinstance(outcome, ChannelReady):
                    outcome.connection.close()
    
>       assert finished, f"await_channel_ready was still blocked after {elapsed:.1f} s"
E       AssertionError: await_channel_ready was still blocked after 4.0 s
E       assert False

tests/e2e/test_channel_readiness_dial.py:153: AssertionError
________ test_a_planted_link_is_refused_without_dialling_what_it_names _________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-529/test_a_planted_link_is_refused0')

    def test_a_planted_link_is_refused_without_dialling_what_it_names(tmp_path: Path) -> None:
        """(b): the reserved name is a link to a host listener; readiness refuses it, and that
        listener has no connection waiting."""
        outside = tmp_path / "outside"
        outside.mkdir()
        host = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        host.bind(str(outside / "host.sock"))
        host.listen(8)
        try:
            jail, reservation, directories = _jail(tmp_path, _PLANTED_LINK, str(outside / "host.sock"))
            try:
                outcome = await_channel_ready(jail, reservation, timeout_s=_DEADLINE_S)
            finally:
                destroy_jail(jail, directories=directories)
            if isinstance(outcome, ChannelReady):
                outcome.connection.close()
            host.setblocking(False)
            try:
                dialled, _ = host.accept()
            except BlockingIOError:
                dialled = None
            if dialled is not None:
                dialled.close()
        finally:
            host.close()
    
        assert isinstance(outcome, ChannelRefused | ChannelNotReady), outcome
>       assert dialled is None, "the host listener behind the link was dialled"
E       AssertionError: the host listener behind the link was dialled
E       assert <socket.socket [closed] fd=-1, family=1, type=1, proto=0> is None

tests/e2e/test_channel_readiness_dial.py:185: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_channel_readiness_dial.py::test_readiness_honours_its_deadline_against_a_full_backlog
FAILED tests/e2e/test_channel_readiness_dial.py::test_a_planted_link_is_refused_without_dialling_what_it_names
2 failed in 4.37s
```

Check `uv run just done` exited 0

(283 earlier lines omitted)
```text
[2m18:51:14.854[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m18:51:14.907[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m18:51:14.918[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m18:51:17.327[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.58s
[2m18:51:17.351[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m18:51:17.354[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.6s[39m[0m

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
INFO    -  Documentation built in 6.31 seconds

== architecture validate: PASS ==
[2m18:51:19.109[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m18:51:19.126[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m18:51:19.160[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m18:51:19.161[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m18:51:19.663[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m18:51:20.003[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m18:51:20.004[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 896ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
