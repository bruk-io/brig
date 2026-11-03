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

Worker, 2026-11-03 (branch claude/create-and-readiness).

What changed:
- infra/sockets.py: `open_directory(path)` returns an O_PATH|O_DIRECTORY|O_NOFOLLOW fd. `channel_ready(directory_fd, name, jail_namespace_fd)` opens the name beneath that fd with O_PATH|O_NOFOLLOW; S_ISLNK is refused as PEER_OUTSIDE_JAIL before any socket exists; anything else that is not S_ISSOCK (a file, a directory, nothing) is ChannelNotReady as before; the socket is connected non-blocking to /proc/self/fd/N, so EAGAIN from a full backlog is ChannelNotReady at once, and the verified connection is set back to blocking before it is handed out (ChannelReady's documented shape). The namespace check is unchanged.
- The deadline: measured on this host that a non-blocking AF_UNIX connect to a full backlog returns EAGAIN, never EINPROGRESS, so there is nothing to poll inside one attempt; the poll until the deadline is await_channel_ready's existing loop, which now cannot be held by one attempt.
- The fd is held from creation: create_bwrap_jail opens it right after `directories.create` (an OSError there is ChannelDirectoryCreateFailed) and puts it on the Jail as `channel_directory_fd`; TASK-0044's `dismantle` closes it, so destroy_jail and a failed create both do. It is opened in the driver, not by ChannelDirectoryPort.create, because changing that port's shape would break recorded repro files that define their own port (test_channel_readiness_battery.py, test_channel_directory_lifecycle.py).
- await_channel_ready asks the port with (jail.channel_directory_fd, reservation.name, jail.channel_namespace_fd); a Jail with no directory fd is the existing ValueError.
- A link at the name reuses PEER_OUTSIDE_JAIL rather than a new reason, so the readiness battery's planted-symlink case passes unchanged; its docstrings say a link is refused so. This changes one fact decision-0005 recorded: a dangling symlink at the name used to read not ready (connect failed) and is now refused.
- Docs: spec (infra sockets bullet and presentation readiness paragraph, with what holds it), glossary readiness, the LikeC4 sockets component and the driver's edge.

Public API change: ChannelReadinessPort.ready(directory_fd, name, jail_namespace_fd) instead of (path, jail_namespace_fd); Jail gains `channel_directory_fd: int | None = None`; infra.sockets.channel_ready takes (directory_fd, name, jail_namespace_fd) and infra.sockets.open_directory is new.

Tests: the recorded repro tests/e2e/test_channel_readiness_dial.py (real bwrap: listen(0) with the jail filling its own backlog, timeout_s=2, came back blocked after 4 s before the fix; a planted link to a host listener left a connection in that listener's backlog). New: tests/e2e/test_channel_readiness_beneath.py (infra: blocking connection handed out, full backlog not ready in under 0.5 s, live and dangling links refused with no connection at the listener, non-sockets not ready, the lookup follows the held directory, not its path) and tests/integration/test_channel_directory_fd.py (the fd names the directory made, and no fd is left after destroy or after a create that fails at the scan). Changed to the new signatures, assertions kept: tests/integration/test_channel_readiness.py, tests/e2e/test_channel_readiness_refusals.py and test_channel_readiness_kernel.py (a helper holds a directory fd per call), and test_channel_reservations.py (the endpoint is compared with the fake's own path). FakeChannelDirectories now makes and removes its directory under a throwaway temp root, since the driver opens what was made.

Commits: 7e43787 (repro), cfba449 (fix). `just done` passed (recorded above), with the same four pre-existing e2e skips as before.

Not verified: a kernel before 6.5, Seatbelt, and setuid bwrap; whether /proc is always mounted where an embedder runs (the dial needs /proc/self/fd, as the namespace check already needs /proc).
<!-- SECTION:NOTES:END -->
