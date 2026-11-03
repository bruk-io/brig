---
id: TASK-0044
title: A failed create_bwrap_jail leaves a running jail nothing can destroy
status: Done
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:57:00Z'
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
- [x] #1 Once the supervisor process exists, every failure inside create_bwrap_jail tears the jail down through the same destroy path destroy_jail uses, and releases placeholders only once teardown reports the process gone
- [x] #2 An integration test with fakes fails each step after the start (placeholder attach, the namespace scan) and asserts the process was destroyed and nothing was released while it lived; recorded failing before the fix
- [x] #3 create_bwrap_jail and destroy_jail share one cleanup function, so the two paths cannot disagree again
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

Worker, 2026-11-03 (branch claude/create-and-readiness).

What changed:
- One cleanup, `dismantle` in src/brig/presentation/jail.py, run by both `destroy_jail` and `create_bwrap_jail`'s failure path (AC#3). With a process it runs `operations.destroy` through the shared driver and closes the supervisor's pipe; then, whatever the ladder found, it removes the script and the channel directory and closes the namespace fd (OSError swallowed); it releases the placeholder record only when the result is GONE. With no process (a failure before the start) the result is GONE and everything is removed and released at once.
- `create_bwrap_jail`: a failure after the start (placeholder attach, the namespace scan, or any BaseException there) tears the jail down through `dismantle`; the step's own error propagates when the group is gone, and `JailTeardownFailed(process)` with that error as `__cause__` when it survives (the embedder has no Jail to destroy, so it must hear the jail still runs). The supervisor's pipe is now closed on a failed create too; it was not before.
- Placeholders go through a new `PlaceholderPort` (hold, attach, release; presentation/ports.py) wired to infra in jail.py as `PLACEHOLDERS`, so a test can fail the attach with a fake. `hold` is always called; the real port returns None for no paths, so nothing is written for a jail with nothing absent.
- An OSError listing proc_root in the namespace scan is now `ChannelNamespaceNotFound` (cause the OSError) instead of an untranslated infra exception (the driver exception boundary rule).
- Docs: spec law 7 and the presentation section, the error docstrings (PlaceholdersFailed, ChannelNamespaceNotFound, JailTeardownFailed), create/destroy docstrings, and the LikeC4 model (api and the bwrap driver no longer import infra.placeholders; jail does, and runs destroy through the driver).

Public API change: `create_bwrap_jail` and `destroy_jail` take `placeholders: PlaceholderPort = PLACEHOLDERS`; `Jail.placeholders` is now `str | None` (the port's record) instead of `Path | None`; `close_namespace_fd` became private (only jail.py uses it now). `PlaceholderPort` is not re-exported from brig (as ProcessPort and SupervisorPort are not); a fake satisfies it structurally.

Tests: the recorded repro tests/integration/test_create_failure_tears_down.py (scan step, group gone after TERM); tests/integration/test_create_failure_cleanup.py adds the attach and scan steps each with the group gone (released after teardown) and alive (JailTeardownFailed, nothing released), a failure before the start (released at once, nothing signalled), and destroy_jail's same gate with FakePlaceholders. FakePlaceholders is in tests/integration/fakes.py.

Commits: 228b298 (repro), 687b660 (fix). `just done` passed (recorded above); one e2e skip, test_spawn_close_action_race, which skips on this host as before.

Not verified: a real-bwrap failure after the start (there is no seam to fail attach or the scan on a real jail; the fake-driven tests cover the path). Not changed: other infra calls in the driver that can still raise an untranslated OSError before the start (the supervisor script write in `_supervisor_path`, `state_dir.ensure_empty`), observed while grepping for the boundary rule, not measured.

Worker, correction to the note above: the full run has four e2e skips, not one, the same four before and after this change (test_spawn_close_action_race, test_supervisor_script_cleanup's bwrap-missing case, and two in test_tiocsti_battery), each skipping for its own documented host reason. Later, TASK-0045 (cfba449) added the channel directory fd to `dismantle`, so the same cleanup closes it.

Check `uv run just done` exited 0

(283 earlier lines omitted)
```text
[2m18:54:38.545[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m18:54:38.547[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m18:54:38.574[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m18:54:40.671[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.29s
[2m18:54:40.693[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m18:54:40.697[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.2s[39m[0m

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
INFO    -  Documentation built in 5.94 seconds

== architecture validate: PASS ==
[2m18:54:42.599[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m18:54:42.619[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m18:54:42.655[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m18:54:42.656[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m18:54:43.261[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m18:54:43.575[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m18:54:43.576[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 977ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Reviewer, 2026-11-03: closed. Full check (record-check --tier full) passed. One dismantle in presentation/jail.py serves destroy_jail and create_bwrap_jail's failure path; placeholders are released only when destroy reports GONE; JailTeardownFailed (cause the step's error) is raised only when a started process survives teardown, which is right since the embedder holds no Jail. PlaceholderPort is a Protocol faked structurally (FakePlaceholders), no patches; not re-exported, consistent with ProcessPort/SupervisorPort. Findings, none filed: (low) dismantle documents 'raises nothing' but an OSError from run(operations.destroy) or supervisors.close would escape and mask the step's error; (low) a failure inside run(operations.create) after the bwrap process spawned leaves process None, so dismantle skips the ladder - pre-existing, outside this task's criteria; (info) the worker's own note of untranslated OSErrors before the start (_supervisor_path, ensure_empty).
<!-- SECTION:NOTES:END -->
