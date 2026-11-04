---
id: TASK-0051
title: >-
  The leader-exits-before-group tests' refreshed Linux measurements do not
  reproduce -- the pre-sleep test is documented vacuous there but discriminates
  150/150
status: In Progress
assignee: []
created_date: 2026-10-18 22:30
updated_date: '2026-11-04T14:18:00Z'
labels:
  - brig
  - tests
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0017 refreshed the docstrings on tests/e2e/test_processes_gateway.py's two test_destroy_jail_survives_the_leader_exiting_before_its_group tests. The load-bearing Linux figure in them does not reproduce.

Both docstrings tell a reader that the ORIGINAL pre-sleep test proves nothing on Linux: 'by 0.05s the leader has already exited and its orphaned sibling has already settled, so the race this test exists to catch never fires: measured at 0/150 JailTeardownFailed with kill_grace_s=0.0 there, identical to the real default. CI runs Linux, so this test alone would not catch a regression of TASK-0001.07's fix.' The no-pre-sleep variant's docstring repeats the same premise as its reason to exist.

Re-measured by the reviewer, twice, in the named image (brig-probe-amd64:latest, privileged, --platform linux/amd64), forcing the grace window off via brig.destroy_jail.__kwdefaults__['kill_grace_s']=0.0 and running the test unmodified: the pre-sleep test failed 150/150, not 0/150. It is the strongest discriminator measured on either platform. The claim in the docstring is the opposite of what the image does.

Why it matters beyond the arithmetic: the docstrings are the only record of which of these two tests catches a TASK-0001.07 regression on the platform CI runs. A maintainer trimming e2e runtime and trusting them would delete the pre-sleep test as dead weight on Linux -- when measured, it is the one that fires hardest there.

Two smaller drifts in the same docstrings, found alongside: the pre-sleep test's docstring says macOS measured 149/150 at kill_grace_s=0.0 (the task description records 145/150; the reviewer measured 150/150), and the no-pre-sleep test's says macOS noise runs '~2% to ~23%' where the implementer reported 2-34% (the reviewer measured 2/40). The macOS figures are directionally right -- strong pin with the pre-sleep, weak and noisy without -- so only the Linux claim is contradicted.

Neither TASK-0016 nor TASK-0017's acceptance criteria are affected: the no-pre-sleep test is decisive on Linux (39/40 with the grace window disabled) and both tests pass against the real default on both platforms. This is a documentation-versus-evidence defect in the docstrings, not a defect in the tests.

Note for whoever picks this up: the reviewer's host runs the amd64 image emulated on Darwin 27, and scheduling under emulation may not be the environment the original 0/150 was taken in. The fix is probably not to swap one number for another but to make each figure carry the host and method that produced it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The docstrings on both test_destroy_jail_survives_the_leader_exiting_before_its_group tests state only Linux measurements that reproduce in brig-probe-amd64:latest, or name the host and method each figure was taken on
- [ ] #2 Whichever of the two tests actually discriminates on Linux is identified correctly, so a maintainer trimming the suite cannot delete the wrong one on the docstring's say-so
- [ ] #3 Every measured figure in test_processes_gateway.py's two leader-exits docstrings names its host, kernel, emulation and method
- [ ] #4 Each docstring says the no-pre-sleep test is the one that discriminates on native Linux (40/40 here, 2026-11-04) and that the pre-sleep test's power depends on the host (0 to 3 in 150 here)
- [ ] #5 No test's behaviour changes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

No repro: this bug is in docstrings only (tests/e2e/test_processes_gateway.py's two leader-exits tests and the no-pre-sleep iteration constant), and no test's behaviour may change (AC#5), so there is no behaviour for a test to fail on. The evidence is the measurement recorded with the change, and an AST comparison showing the module's code, docstrings aside, is unchanged.

Check `uv run just done` exited 0

(349 earlier lines omitted)
```text
[2m14:02:40.457[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m14:02:40.497[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m14:02:40.498[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m14:02:42.297[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.01s
[2m14:02:42.300[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m14:02:42.303[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.1s[39m[0m

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
INFO    -  Documentation built in 5.64 seconds

== architecture validate: PASS ==
[2m14:02:44.199[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m14:02:44.214[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m14:02:44.237[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m14:02:44.238[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m14:02:44.646[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m14:02:44.915[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m14:02:44.916[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 717ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Worker, 2026-11-04 (branch claude/small-bugs): change 1f2d75d, docstrings only.

Remeasured on this host: an x86_64 Firecracker microVM under KVM (hardware virtualisation, no CPU emulation), 4 vCPUs (Intel Xeon 2.10GHz), kernel 6.18.44-fc-v233, Ubuntu 24.04.5 userland in a container, Python 3.15.0b4, pytest 9.1.1, shared with other sessions' work (load average 3.8 to 5). brig-probe-amd64:latest could not be run here (no Docker daemon). Method: each test unmodified, one pytest run per figure, with a measurement-only pytest plugin outside the repository setting `brig.destroy_jail.__kwdefaults__["kill_grace_s"] = 0.0` at configure time; the count read from the test's own assertion message.

- kill_grace_s forced to 0.0: pre-sleep test 0, 2 and 4 of 150 (three runs); no-pre-sleep test 38, 40, 40 and 40 of 40 (four runs).
- real default: pre-sleep 0 of 150 and no-pre-sleep 0 of 40, three runs each.

These agree with the lead's figures (pre-sleep 0, 1, 3 of 150; no-pre-sleep 40 of 40), so on native Linux the no-pre-sleep test is the discriminator and the pre-sleep test is weak; the reviewer's 150/150 under emulation and the macOS figures show its power depends on the host.

- AC#1/#3: every figure in both docstrings now names its host, kernel (or that it was not recorded), emulation and method, and who measured it. Provenance taken from the board: 145/150, 0/150 (image, pre-sleep) and 200/200 from TASK-0017's description (TASK-0013's review); 150/150, 39/40 and 2/40 from TASK-0017's reviewer; 2% to 34% from TASK-0017's implementer as reported. The old 149/150 has no run on the board; it is kept and labelled so. The lead's figures carry no method beyond kill_grace_s=0.0, so they are not labelled "forced".
- AC#2/#4: each docstring says the no-pre-sleep test discriminates on native Linux (40 of 40 here) and the pre-sleep test's power depends on the host (0 to 4 in 150 here, 0 to 3 in the lead's runs). `_LEADER_EXITS_BEFORE_GROUP_NO_PRE_SLEEP_ITERATIONS`'s docstring, which repeated the 200/200 figure, now points at the test's docstring for host and method.
- AC#5: the module's AST with docstrings stripped is identical to f4605ae's.
- `uv run just done`: all steps passed (recorded above). Criteria left for the reviewer.

Check `uv run just done` exited 0

(350 earlier lines omitted)
```text
[2m14:18:03.318[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m14:18:03.320[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m14:18:03.322[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m14:18:05.785[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.56s
[2m14:18:05.790[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m14:18:05.793[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.2s[39m[0m

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
INFO    -  Documentation built in 5.63 seconds

== architecture validate: PASS ==
[2m14:18:07.293[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m14:18:07.404[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m14:18:07.474[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m14:18:07.475[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m14:18:07.976[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m14:18:08.341[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m14:18:08.341[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
