---
id: TASK-0041
title: >-
  Bring the LikeC4 model up to what is built: the supervisor, placeholders,
  files and the bwrap slice
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T04:39:00Z'
updated_date: '2026-11-03T04:50:00Z'
labels:
  - size-3
dependencies: []
type: task
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0037's review, 2026-11-03. docs/architecture still tags the supervisor and its wire #planned ('designed, not built'; the containers view's title says so), the components view says the supervisor has no code to show, and the model has no element for infra/placeholders.py, infra/files.py, presentation/jail.py or presentation/driver.py (decision-0007 item 5 moved the effect interpreter there). Seatbelt's two elements are rightly #planned. Update the model in orthodox C4 with the c4-architecture plugin's rules, so its views match src/brig.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No built component or relationship is tagged #planned, and every module under src/brig has a component (or is named in one) in the model
- [x] #2 likec4 validate and c4lint are clean (uv run just done passes)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files that change: docs/architecture/models/brig/{supervisor.c4,_relationships.c4}, models/brig/library/*.c4 (existing descriptions brought to the code; new components: channels, grades, policy, files, placeholders, state-dir, supervisor-link, driver, jail, report), views/brig/{components,containers,jail-types}.c4, docs/architecture/index.md.

### Order of work
1. Inventory src/brig by module against the model (c4-components rules: one component per module behind its own interface, a package or tight module group as one component where it has one interface: domain/policy/* as Policy, claims.py + grades.py as Grades, infra/supervisor/{link,assemble,wire}.py as Supervisor Link; presentation/driver.py, jail.py, report.py each their own).
2. Supervisor container: drop #planned and the 'not built' wording; describe it as built (wire.py + program.py assembled, PID 1, non-dumpable per decision-0006). Not decomposed: one small program whose parts are code; program.py and wire.py are named in Supervisor Link, which assembles them.
3. Library components: add the new ones, rewrite stale descriptions (effects, plan, processes, sockets, bwrap jail type, bwrap driver, api, ports) to what the code does; Seatbelt stays #planned, its descriptions aligned to decision-0007 (profile from FsPolicy, starts through the shared driver); oci stays #paused.
4. Relationships from the imports: replace the container-level #planned edge with Supervisor Link -> supervisor (technology stated); drop edges the code no longer has (api -> bwrapDriver, api -> bwrapJailType, api -> processes, bwrapDriver -> processes); add every new import edge.
5. Views: component view groups gain the new components, comments and titles lose 'not yet built'; containers view title plain.
6. index.md: Containers and Components sections describe what is built.
7. uv run just done; commit; report and record-check.

### Risks
- c4lint forbids a component from another container in a component view; the cross-container edge goes component -> container (supervisor), so the library view shows the supervisor container, not a component of it.
- Edge density in the component view: every edge stays because it is an import in src; titles kept short.
- just done also runs tests/e2e (bwrap); a failure there is not the model's and is reported, not fixed here.

### Proof
- grep shows no #planned outside seatbelt-*.c4 and no 'not built'/'planned' wording on built elements.
- A per-module check: every src/brig module path is named in a .c4 file.
- uv run just done green (likec4 validate, c4lint, mkdocs --strict among its steps).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Worker's report (@claude, 2026-11-03)

Done in docs/architecture only; no code changed.

- Supervisor container: #planned and the 'designed, not built' wording gone; described as built (wire.py + program.py assembled by assemble.py, PID 1, non-dumpable per decision-0006). Not decomposed: one ~180-line program with no interface inside it, so its parts are code; program.py and wire.py are named in the Supervisor Link component, which assembles them.
- Library components added: Channels, Grades (claims.py + grades.py), Policy (domain/policy/*), Host Files, Placeholders, State Directory, Supervisor Link (link/assemble/wire), Driver (presentation/driver.py, the shared effect interpreter), Jail (presentation/jail.py), Report. API is now api.py alone; Bwrap Driver is drivers/bwrap.py alone. Stale descriptions (effects, plan, processes, sockets, ports, bwrap jail type) brought to the code (FsPolicy intent compiled to mounts, decision-0007; ceilings as the report, decision-0008).
- Relationships rebuilt from src/brig's imports (50): the #planned container edge replaced by Supervisor Link -> supervisor (technology stated; library -> supervisor is derived from it); api -> bwrapDriver, api -> bwrapJailType, api -> processes and bwrapDriver -> processes dropped (no such import now).
- Views: containers title plain; components view groups the new components and shows the supervisor as a container. index.md's Containers and Components sections rewritten to what is built.
- Seatbelt stays #planned (descriptions aligned to decision-0007 items 5-6); oci stays #paused.
- Every module under src/brig is named in a .c4 file (checked by grep over each path); package __init__.py files are re-export barrels, noted in library.c4.

Gate: uv run just done, all 11 steps PASS (likec4 validate; c4lint 0 errors, 0 warnings, 30 elements, 50 relationships, 5 views; mkdocs --strict).

Check `uv run just done` exited 0

(264 earlier lines omitted)
```text
[2m04:47:30.395[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m04:47:30.414[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:47:30.415[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:47:32.663[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.43s
[2m04:47:32.666[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-model/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:47:32.671[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.4s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig-model/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-model/docs
INFO    -  Documentation built in 6.22 seconds

== architecture validate: PASS ==
[2m04:47:34.755[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:47:34.792[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-model/docs/architecture[0m
[2m04:47:34.840[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:47:34.841[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:47:35.505[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m04:47:36.076[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m04:47:36.076[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.3s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 50 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Check `uv run just done` exited 0

(258 earlier lines omitted)
```text
[2m04:50:03.454[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m04:50:03.456[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:50:03.498[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:50:06.006[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.67s
[2m04:50:06.009[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:50:06.013[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.6s[39m[0m

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
INFO    -  Documentation built in 6.68 seconds

== architecture validate: PASS ==
[2m04:50:08.069[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:50:08.089[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m04:50:08.155[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:50:08.158[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:50:08.774[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m04:50:09.152[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m04:50:09.153[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 50 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
