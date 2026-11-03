---
id: TASK-0046
title: >-
  Errors that still escape create_bwrap_jail untranslated, and a dismantle that
  can mask the step's error
status: Done
assignee: []
created_date: '2026-11-03T18:58:00Z'
updated_date: '2026-11-03T19:23:00Z'
labels:
  - brig
  - errors
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0044/0045's worker and review (2026-11-03): (1) writing the supervisor script (_supervisor_path) and state_dir.ensure_empty can raise a bare OSError out of create_bwrap_jail, past the driver-exception-boundary rule; (2) dismantle's docstring says it raises nothing, but an OSError from run(operations.destroy) or supervisors.close would escape and hide the failed step's own error; (3) if run(operations.create) itself raises after bwrap has spawned, process is still None and the kill ladder is skipped (true before TASK-0044 too).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every OSError create_bwrap_jail can raise before the start (writing the supervisor script, preparing the state directory) crosses as one of presentation/errors.py's types, with the OSError as its cause; integration tests with fakes pin each; recorded failing before the fix
- [x] #2 dismantle never hides the failed step's error: a teardown or close failure inside it is attached to the step's error (add_note or a chained cause) or raises JailTeardownFailed, and its docstring says which
- [x] #3 If operations.create raises after bwrap has spawned, the spawned process is still torn down (the create effect hands back what it spawned, or the driver reaps by pidfd); a test with a fake that spawns then fails pins it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).

Repro at e14be84ae900, test files: tests/integration/test_create_error_edges.py; command: `uv run pytest tests/integration/test_create_error_edges.py -q` exited 1

(98 earlier lines omitted)
```text
E       AssertionError: PermissionError(1, "fake host: the teardown's signal was refused")
E       assert False
E        +  where False = isinstance(PermissionError(1, "fake host: the teardown's signal was refused"), JailTeardownFailed)
E        +    where PermissionError(1, "fake host: the teardown's signal was refused") = <ExceptionInfo PermissionError(1, "fake host: the teardown's signal was refused") tblen=5>.value

tests/integration/test_create_error_edges.py:141: AssertionError
____________ test_a_close_that_raises_does_not_hide_the_steps_error ____________

    def test_a_close_that_raises_does_not_hide_the_steps_error() -> None:
        """The attach fails, the teardown reads the group gone after TERM, and closing the
        supervisor's pipe raises: the attach's own `PlaceholdersFailed` still propagates, with the
        close's failure attached to it, and the placeholders are released."""
        processes = FakeProcesses(alive_checks=1)
        supervisors = FakeSupervisors(fail_close=True)
        placeholders = FakePlaceholders(fail_attach=True)
    
        with pytest.raises(BaseException) as raised:
            create_bwrap_jail(
                ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
            )
    
>       assert isinstance(raised.value, PlaceholdersFailed), repr(raised.value)
E       AssertionError: OSError(5, "fake host: the supervisor's pipe could not be closed")
E       assert False
E        +  where False = isinstance(OSError(5, "fake host: the supervisor's pipe could not be closed"), PlaceholdersFailed)
E        +    where OSError(5, "fake host: the supervisor's pipe could not be closed") = <ExceptionInfo OSError(5, "fake host: the supervisor's pipe could not be closed") tblen=4>.value

tests/integration/test_create_error_edges.py:163: AssertionError
___ test_a_start_that_spawned_then_failed_tears_the_spawned_supervisor_down ____

    def test_a_start_that_spawned_then_failed_tears_the_spawned_supervisor_down() -> None:
        """The port's start spawned the supervisor and then failed: `JailSpawnFailed` still
        propagates, and before it does the spawned supervisor's group was verified, sent TERM,
        verified gone, its pid released and its pipe closed."""
        processes = FakeProcesses(alive_checks=1)
        supervisors = FakeSupervisors(fail_after_start=True)
        placeholders = FakePlaceholders()
    
        with pytest.raises(BaseException) as raised:
            create_bwrap_jail(
                ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
            )
    
        assert isinstance(raised.value, JailSpawnFailed), repr(raised.value)
        assert supervisors.spawned == [_SUPERVISOR_PID]
>       assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
E       assert [] == [(2000, <Sign...SIGTERM: 15>)]
E         
E         Right contains one more item: (2000, <Signals.SIGTERM: 15>)
E         Use -v to get more diff

tests/integration/test_create_error_edges.py:185: AssertionError
=========================== short test summary info ============================
FAILED tests/integration/test_create_error_edges.py::test_a_state_directory_that_cannot_be_made_crosses_as_brigs_own_error
FAILED tests/integration/test_create_error_edges.py::test_an_empty_directory_that_is_not_empty_crosses_as_brigs_own_error
FAILED tests/integration/test_create_error_edges.py::test_a_supervisor_script_that_cannot_be_written_crosses_as_brigs_own_error
FAILED tests/integration/test_create_error_edges.py::test_a_teardown_that_raises_does_not_hide_the_steps_error
FAILED tests/integration/test_create_error_edges.py::test_a_close_that_raises_does_not_hide_the_steps_error
FAILED tests/integration/test_create_error_edges.py::test_a_start_that_spawned_then_failed_tears_the_spawned_supervisor_down
6 failed in 0.60s
```

Check `uv run just done` exited 0

(292 earlier lines omitted)
```text
[2m19:17:50.725[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m19:17:50.731[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m19:17:50.794[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m19:17:53.131[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.57s
[2m19:17:53.135[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m19:17:53.138[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.7s[39m[0m

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
INFO    -  Documentation built in 6.90 seconds

== architecture validate: PASS ==
[2m19:17:55.067[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m19:17:55.085[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m19:17:55.116[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m19:17:55.117[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m19:17:55.654[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m19:17:56.015[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m19:17:56.016[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 949ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Worker, 2026-11-03: repro e14be84, fix 7ecff69 (branch claude/error-edges). Criteria left unticked for the reviewer.

**Repro.** `tests/integration/test_create_error_edges.py`, recorded failing above, each on an assertion about what crossed. The fakes gained the failures it needs (a refused TERM, a close that raises, a start that spawns then fails). Today's port had no way to say "I spawned this, then failed", so in the repro commit `FakeSupervisors(fail_after_start=True)` records the spawn and raises `OSError`, as the real port did. The fix changes only the fake's way of reporting (`JailSpawnFailed` carrying the `Process`, the new port contract). The repro file is unchanged. Edge 1 can't be faked in-process: nothing sits between the driver and the state directory, root ignores permissions, and `resolved_state_dir` is cached per process and shared with every jail on the host. So each host failure is real, in a child Python with its own `BRIG_HOME`, using the fakes: the state directory under a regular file, an `empty` directory that holds a file, and a 1 KiB `RLIMIT_FSIZE` that stops the script's write (`EFBIG`).

**#1 (bare OSErrors before the start).** New type `StateDirectoryWriteFailed(path)`, exported from `brig`. No existing type fit. `StateDirectoryInvalid` is a refused `BRIG_HOME` value, found before any I/O. `ChannelDirectoryCreateFailed` and `PlaceholdersFailed` name other things. Wrapped: `ensure_empty` (path `<state>/empty`), the script write (path: the state directory; a part-written script is unlinked), and `resolved_state_dir`'s own `ensure`, which also prepares the state directory and raised bare too. `reserve_channels` now raises the typed error there as well.

**#2 (dismantle hides the step's error).** `dismantle` returns `_Dismantled(state, ladder_error, close_error)` and raises nothing. It catches `Exception` from the kill ladder and from `supervisors.close`. A ladder that raised reads as `ALIVE`, since the group was never verified gone, so placeholders are kept. A failed create adds each error to the step's error with `add_note`, and raises `JailTeardownFailed` from that step error on `ALIVE`. `destroy_jail` raises `JailTeardownFailed` from the ladder's error (it used to let a bare OSError out), and swallows a close failure as it swallows every other cleanup's. The docstrings say which.

**#3 (spawned, never stopped).** I took the simplest shape: the start hands back what it spawned. `link.SupervisorSpawnError.spawned` is `(pid, pgid)` when the start failed after the spawn (pumps that could not start, or a request write that hit `EPIPE`). `link` no longer blocks in `waitpid` on a supervisor it never signalled; it hands it over unsignalled and unreaped. The driver turns that into `JailSpawnFailed(argv, process)`, and a port may raise that itself. `create_bwrap_jail` takes `error.process` and tears it down through the verified ladder. The other option, the port reaping its own child, would put an unverified kill in infra, beside the domain's verified ladder (decision-0001 rule 10). E2e gateway `tests/e2e/test_supervisor_link_spawned_then_failed.py` pins the infra half with a stand-in supervisor that closes `REQUEST_FD` and sleeps. Before the fix it blocked 30 s in `waitpid`, then failed.

**Public API changes.** `StateDirectoryWriteFailed` (new). `JailSpawnFailed(argv, process=None)` gains `.process`. `Process` is exported. `SupervisorPort.start` documents raising `JailSpawnFailed` with `process` set. `destroy_jail` raises `JailTeardownFailed` (not a bare OSError) when the ladder raises.

**Later tests.** `tests/integration/test_create_error_edges_types.py` pins the exact type, the path it names, and that no partial script is left. It also covers a spawned-then-failed start whose teardown fails (`JailTeardownFailed` from `JailSpawnFailed`, placeholders kept), and both `destroy_jail` paths.

**Found, not fixed (follow-up?).** Other pre-start OSErrors can still escape `create_bwrap_jail` bare. `_files.facts` calls `os.stat`, which raises `PermissionError` or `ELOOP` for a policy path the embedder cannot search; only not-found is caught. `_files.link_chain` calls `os.readlink`, which can lose a race. And `assemble.assembled_source()` reading brig's own installed sources is inside the script write's `try`, so a broken install would read as `StateDirectoryWriteFailed`. A `KeyboardInterrupt` between the spawn and the end of `link._start` is still not handed back (only `OSError` and `RuntimeError` are).

Check `uv run just done` exited 0

(291 earlier lines omitted)
```text
[2m19:22:31.745[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m19:22:31.766[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m19:22:31.801[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m19:22:33.920[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.30s
[2m19:22:33.923[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m19:22:33.925[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.3s[39m[0m

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
INFO    -  Documentation built in 6.61 seconds

== architecture validate: PASS ==
[2m19:22:36.120[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m19:22:36.142[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m19:22:36.177[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m19:22:36.179[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m19:22:36.753[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m19:22:37.053[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m19:22:37.054[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 936ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Reviewer, 2026-11-03: closed. Full check (record-check --tier full) exit 0, nothing reformatted. e2e tests/e2e/test_supervisor_link_spawned_then_failed.py passes in real /usr/bin/bwrap; repro and type tests pass. Repro fake change: at e14be84 FakeSupervisors(fail_after_start=True) raised OSError after recording a spawn, which is what the real link did then (it waited on the child and raised SupervisorSpawnError with nothing handed back); the recorded failure is signalled == [], i.e. the spawned process was never torn down. That is the bug. The fix changed the port contract, and the fake follows it. The real port's half is held by the e2e test. Accepted. Edge 1 in child Pythons: real host failures (ENOTDIR, a non-empty empty dir, EFBIG under RLIMIT_FSIZE) against real brig code with fake ports, isolated because resolved_state_dir is cached per process. That is real evidence, stronger than a fake. API: StateDirectoryWriteFailed is in presentation/errors.py; Process is domain plain data, which __init__ may re-export (decision-0001 layout, like ExitCodeUnknown); JailSpawnFailed.process is optional. destroy_jail's JailTeardownFailed in place of a bare OSError is stated in its docstring, JailTeardownFailed's docstring and the spec section 7. Minor, not filed: no changelog exists to note the destroy_jail change; KeyboardInterrupt between spawn and the end of link._start is still not handed back (the worker noted it). Filed DRAFT-0030 for files.facts/link_chain bare OSErrors and assembled_source read misreported as StateDirectoryWriteFailed.
<!-- SECTION:NOTES:END -->
