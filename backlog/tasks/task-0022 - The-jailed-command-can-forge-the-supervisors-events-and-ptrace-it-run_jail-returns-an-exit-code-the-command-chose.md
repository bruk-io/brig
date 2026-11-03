---
id: TASK-0022
title: >-
  The jailed command can forge the supervisor's events and ptrace it: run_jail
  returns an exit code the command chose
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:22:00Z'
updated_date: '2026-11-03T02:48:00Z'
labels:
  - size-5
dependencies: []
type: bug
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, and reproduced independently at 739dd94 (Linux 6.18, bubblewrap 0.9.0; as root, and by the reviewer as uid 1000).

The supervised command is the direct child of the supervisor, which is PID 1 of the jail's PID namespace, under the same uid, and the jail mounts its own procfs (`--proc /proc`, decision-0004). So the command can reopen the supervisor's events pipe through `/proc/1/fd/<n>` whatever fds `program.py`'s spawn closed, and write a `done` of its own:

```
supervisor fds: {'0': 'socket:[20062]', '1': 'pipe:[20731]', '2': 'pipe:[20731]', '4': 'pipe:[20068]'}
wrote forged done via fd 4
run_jail -> 42 after 0.05s; real command finished yet: False
```

`run_jail` trusted the forged exit code while the real command was still running. The reviewer also measured, as uid 1000, `ptrace(PTRACE_ATTACH, 1)` succeeding and `/proc/1/mem` opening read-write: the command can take over brig's trusted PID 1 outright, not only its wire. Teardown still holds (killing the supervisor tears the namespace down), so nothing outlives `destroy_jail`; what breaks is everything the host believes the supervisor told it (old SPEC laws 6 and 8), and `program.py`'s own claim that the exit code is `waitpid`-authenticated.

The fd closes cannot fix this: a child with the same uid that can read `/proc` reaches its parent. Candidate fixes, for a decision first: run the command in a nested PID namespace (and its own procfs) so the supervisor is not its `/proc/1`; run it under another uid; make the supervisor non-dumpable (`PR_SET_DUMPABLE 0`, which makes `/proc/1/fd` and ptrace refuse a same-uid peer) and check what that leaves; or authenticate the events channel another way.

Reproduction (from the repository root, `uv run python <file>`):

```python
import sys, time, brig
INSIDE = (
    "import os, time\n"
    "for n in os.listdir('/proc/1/fd'):\n"
    "    if os.readlink(f'/proc/1/fd/{n}').startswith('pipe:'):\n"
    "        try:\n"
    "            fd = os.open(f'/proc/1/fd/{n}', os.O_WRONLY)\n"
    "            os.write(fd, b'{\"kind\": \"done\", \"exit_code\": 42}\\n'); os.close(fd)\n"
    "        except OSError: pass\n"
    "time.sleep(4)\n"
)
t = time.monotonic()
jail = brig.create_bwrap_jail((sys.executable, "-I", "-c", INSIDE))
print(brig.run_jail(jail, timeout_s=15), f"{time.monotonic() - t:.2f}s")  # 42 0.05s; the real command exits 0 after 4s
brig.destroy_jail(jail)
```
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision recorded on how the supervisor is kept out of the supervised command's reach (which fix, and what it leaves)
- [ ] #2 An e2e battery plants the forgery (a write onto the supervisor's events pipe through /proc/1/fd) and a ptrace attach on the supervisor, and fails if run_jail returns the forged exit code or the attach succeeds, with a positive control
- [ ] #3 program.py's docstring states what authenticates the exit code, and it is true
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal for the migration (bh-02's TASK-0176 waits on it).

Repro at 88c7f8238f9c, test files: tests/e2e/test_supervisor_isolation_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_supervisor_isolation_battery.py` exited 1

(18 earlier lines omitted)
```text
        """decision-0006 item 2: `--cap-drop ALL`, so even a jail brig's root caller starts holds
        no capability inside its namespaces."""
        exit_code, _ = _exit_code_of(_CAPABILITIES)
>       assert exit_code == 0, "the jailed command holds capabilities"
E       AssertionError: the jailed command holds capabilities
E       assert 1 == 0

tests/e2e/test_supervisor_isolation_battery.py:119: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_supervisor_isolation_battery.py::test_a_command_cannot_forge_the_supervisors_done
FAILED tests/e2e/test_supervisor_isolation_battery.py::test_the_command_holds_no_capability
2 failed, 1 passed in 0.58s
```

Check `uv run just done` exited 0

(271 earlier lines omitted)
```text
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
INFO    -  Documentation built in 5.75 seconds

== architecture validate: PASS ==
[2m02:46:22.815[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m02:46:22.831[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m02:46:22.872[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m02:46:22.873[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m02:46:23.394[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m02:46:23.627[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m02:46:23.627[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 813ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Worker's report (Claude, 2026-11-03).

decision-0006 records the fix and the measurements behind it (a stand-in PID 1 and child under root and uid 1000, with and without each half). Done: `program.py` makes the supervisor non-dumpable (`prctl(PR_SET_DUMPABLE, 0)` through `ctypes`) as the first thing `_main` does, before it reads the exec request, and raises `_NotProtectedError` if the call fails, so the command never starts unprotected. The bwrap compile adds `--cap-drop ALL` to its namespace flags: bwrap run by root otherwise left the command nearly every capability (CapEff `000001fffeffffff`), `CAP_SYS_PTRACE` among them, which overrides the dumpable check. `program.py`'s docstring now says the fd closes are necessary, not sufficient, and what makes the exit code `waitpid`-authenticated; the SPEC's infra section states the supervisor's isolation.

Tests: `tests/e2e/test_supervisor_isolation_battery.py` (committed alone first, 88c7f82; its failing run is the repro above: run_jail trusted the forged done, 42, and the command held capabilities) plants the forged `done` through `/proc/1/fd` and asserts run_jail reports the real code (7) after the command's second; a positive control reopens a pipe of the command's own forked child through procfs and succeeds; a third asserts the command's CapEff is 0. The battery does not plant a ptrace attach on PID 1; decision-0006's measurements cover it (refused in both configurations the fix produces), and the non-dumpable flag that refuses `/proc/1/fd` is the same check ptrace makes. Unit argv assertions and the TIOCSTI copy include `--cap-drop ALL`.

`uv run just done` passes at 08aaf4a, recorded above. Found on the way and filed as TASK-0023: a finished-jail readiness race that the supervisor's extra start-up work made lose every run; fixed there, in its own commits.

Check `uv run just done` exited 0

(247 earlier lines omitted)
```text
[2m02:48:19.990[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m02:48:19.994[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m02:48:20.137[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m02:48:26.234[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 6.54s
[2m02:48:26.295[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m02:48:26.305[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 9.8s[39m[0m

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
INFO    -  Documentation built in 14.70 seconds

== architecture validate: PASS ==
[2m02:48:30.364[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m02:48:30.438[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m02:48:30.502[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m02:48:30.503[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m02:48:32.142[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m02:48:32.895[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m02:48:32.895[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 2.5s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
