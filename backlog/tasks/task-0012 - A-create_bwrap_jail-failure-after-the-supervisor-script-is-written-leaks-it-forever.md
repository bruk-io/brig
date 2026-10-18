---
id: TASK-0012
title: >-
  A create_bwrap_jail failure after the supervisor script is written leaks it
  forever
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 16:16'
updated_date: '2026-10-18 17:25'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - src/brig/presentation/api.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
--------------------------------------------------
TASK-0001.21 ties supervisor-script cleanup to destroy_jail's own GroupState.GONE verification, which presupposes a Jail was returned to carry the file's path. If create_bwrap_jail's own run() raises (e.g. JailSpawnFailed, measured concretely on this macOS host: bwrap itself fails to spawn with FileNotFoundError since bwrap isn't installed here) AFTER _supervisors_for has already written the fresh supervisor script but BEFORE a Jail is ever constructed and returned, nothing ever deletes that file -- no Jail exists for any later destroy_jail call to act on. Confirmed not hypothetical: 22 such orphan files (35K each) were found already sitting in this host's real ~/.brig, consistent with this exact path having been hit repeatedly by prior test/agent activity on a bwrap-less macOS host this session. Candidate fix: wrap the write+spawn in a try that deletes the just-written file on any exception before it propagates, inside _supervisors_for or create_bwrap_jail itself, rather than only at the Jail-carries-it-to-destroy_jail stage.

Second shape, found reviewing TASK-0001.21's own close: destroy_jail deletes the script only after confirming GroupState.GONE -- a teardown that never reaches that (raises JailTeardownFailed, the kill ladder's last verify still found the group alive) leaks the script permanently too, with nothing to sweep it. Same unswept-file family as the create-time-failure shape above, different trigger.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A create_bwrap_jail call whose own run() raises before returning a Jail does not leave its freshly-written supervisor script behind
- [x] #2 A test reproduces this exact shape (a failing supervisor spawn, e.g. via a fake/fixture that fails after the script write) and asserts the file is gone
- [x] #3 A destroy_jail call that raises JailTeardownFailed (the kill ladder's last verify still found the group alive) does not leave the jail's own supervisor script behind either, or a decision record says why that shape stays accepted
- [x] #4 A test reproduces the JailTeardownFailed shape and asserts on the chosen outcome
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. In `_supervisors_for`/`create_bwrap_jail`'s flow, wrap the write-then-use
   sequence so the just-written supervisor script is deleted on any exception
   that would otherwise propagate before a `Jail` is ever constructed and
   returned (covers both named shapes: create_bwrap_jail's own run() raising
   JailSpawnFailed, and a destroy_jail that raises JailTeardownFailed without
   ever reaching GroupState.GONE -- the second needs its own try/except around
   the teardown-failure path in destroy_jail, deleting the script on that
   failure too, since no later call will ever get another chance).
2. Tests for both shapes: a fake/fixture that fails the supervisor spawn after
   the script write (asserts the file is gone); a fixture that makes teardown
   never reach GroupState.GONE (asserts the file is gone despite
   JailTeardownFailed being raised).

### Proof
- just gates, just typecheck, just done green.
- Real Linux + bwrap (brig-probe-amd64:latest): confirm no leftover file in a
  fresh BRIG_HOME after deliberately forcing both failure shapes.

### Risks
- Don't let cleanup-on-failure mask or swallow the real exception an embedder
  needs to see (JailSpawnFailed/JailTeardownFailed must still propagate) --
  the file deletion is a side effect alongside the raise, never a replacement
  for it.
- JailTeardownFailed's own case: deleting the script while the jail's group
  might still genuinely be alive (that's exactly what the failure means) is
  still safe for the SAME reason TASK-0001.21's design relies on -- the file
  itself doesn't need the process alive, only not-yet-execed-when-deleted, and
  by this point it was already exec'd (if it ever would be) long before
  teardown started. State that reasoning explicitly rather than leaving it
  implicit, since it's the one subtle part of this task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Check `uv run just done` exited 0

(203 earlier lines omitted)
```text
[2m17:25:40.941[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m17:25:40.941[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m17:25:40.942[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m17:25:40.942[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m17:25:40.946[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m17:25:41.206[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 271ms
[2m17:25:41.208[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m17:25:41.209[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 485ms[39m[0m

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
INFO    -  Building documentation to directory: /Users/brukhabtu/Downloads/brig-seed/site
INFO    -  mkdocs-likec4: Generating web component for default project from /Users/brukhabtu/Downloads/brig-seed/docs
INFO    -  Documentation built in 1.78 seconds

== architecture validate: PASS ==
[2m17:25:42.269[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m17:25:42.273[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m17:25:42.282[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m17:25:42.282[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m17:25:42.401[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m17:25:42.483[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m17:25:42.483[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 215ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```
<!-- SECTION:NOTES:END -->
