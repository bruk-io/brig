---
id: TASK-0044
title: A failed create_bwrap_jail leaves a running jail nothing can destroy
status: In Progress
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:43:00Z'
labels:
  - brig
  - lifecycle
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (reasoned from code): in presentation/drivers/bwrap.py, once run(operations.create...) started the supervisor, _placeholders.attach or _namespace_fd_for can still raise (ChannelNamespaceNotFound is documented 'with process still running'). The except path unlinks the script, removes the channel directory and releases placeholders while the jail still mounts over them, and never tears the process down; the embedder gets no Jail to destroy. Proposed: once a process exists, the failure path runs operations.destroy and releases placeholders only on GONE; share one cleanup with destroy_jail.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Once the supervisor process exists, every failure inside create_bwrap_jail tears the jail down through the same destroy path destroy_jail uses, and releases placeholders only once teardown reports the process gone
- [ ] #2 An integration test with fakes fails each step after the start (placeholder attach, the namespace scan) and asserts the process was destroyed and nothing was released while it lived; recorded failing before the fix
- [ ] #3 create_bwrap_jail and destroy_jail share one cleanup function, so the two paths cannot disagree again
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).

Repro at 228b2980782d, test files: tests/integration/test_create_failure_tears_down.py; command: `uv run pytest tests/integration/test_create_failure_tears_down.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
________ test_a_failed_namespace_scan_tears_the_started_supervisor_down ________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-520/test_a_failed_namespace_scan_t0')

    def test_a_failed_namespace_scan_tears_the_started_supervisor_down(tmp_path: Path) -> None:
        """The scan finds no PID 1 under a running supervisor: `ChannelNamespaceNotFound` still
        propagates, and before it does the supervisor's group was verified, sent TERM, verified
        gone and its pid released, and its events pipe closed."""
        proc_root = str(tmp_path / "proc")
        plant_fake_proc(proc_root, {_SUPERVISOR_PID: (1, str(_SUPERVISOR_PID))})
        directories = FakeChannelDirectories()
        processes = FakeProcesses(alive_checks=1)
        supervisors = FakeSupervisors()
        reserved = reserve_channels((Channel("ctl"),), directories=directories)
    
        with pytest.raises(ChannelNamespaceNotFound):
            create_bwrap_jail(
                ("server",),
                channels=reserved,
                processes=processes,
                supervisors=supervisors,
                directories=directories,
                proc_root=proc_root,
            )
    
>       assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
E       assert [] == [(2000, <Sign...SIGTERM: 15>)]
E         
E         Right contains one more item: (2000, <Signals.SIGTERM: 15>)
E         Use -v to get more diff

tests/integration/test_create_failure_tears_down.py:51: AssertionError
=========================== short test summary info ============================
FAILED tests/integration/test_create_failure_tears_down.py::test_a_failed_namespace_scan_tears_the_started_supervisor_down
1 failed in 5.11s
```

Check `uv run just done` exited 0

(277 earlier lines omitted)
```text
[2m18:42:55.310[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m18:42:55.312[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m18:42:55.373[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m18:42:57.718[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.50s
[2m18:42:57.721[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m18:42:57.725[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.6s[39m[0m

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
INFO    -  Documentation built in 6.28 seconds

== architecture validate: PASS ==
[2m18:42:59.840[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m18:42:59.866[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m18:42:59.897[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m18:42:59.898[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m18:43:00.605[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m18:43:00.966[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m18:43:00.967[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.1s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
