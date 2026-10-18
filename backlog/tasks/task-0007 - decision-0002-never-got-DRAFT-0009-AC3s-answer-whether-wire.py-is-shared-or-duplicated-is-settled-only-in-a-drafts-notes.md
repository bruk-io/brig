---
id: TASK-0007
title: >-
  decision-0002 never got DRAFT-0009 AC#3's answer: whether wire.py is shared or
  duplicated is settled only in a draft's notes
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 08:08'
updated_date: '2026-10-18 14:46'
labels:
  - brig
  - size-1
dependencies: []
modified_files:
  - >-
    backlog/decisions/decision-0002 -
    The-supervisor-request-channels-and-the-grading-skeleton-the-next-slices-shape.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
DRAFT-0009 AC#3 reads: 'decision-0002 says explicitly whether wire.py is shared by the host end (link.py) or duplicated, consistent with rule 17.' It is ticked, and the substance was genuinely settled during TASK-0001.15 step 3 (shared by import on the host side -- link.py does 'from brig.infra.supervisor import wire'; duplicated by convention on the jail side, since program.py assembles into a standalone stdlib-only file with no installed brig package to import from). But that settlement lives only in DRAFT-0009's own Implementation Notes. Evidence: grep of 'backlog/decisions/decision-0002 - The-supervisor-request-channels-and-the-grading-skeleton-the-next-slices-shape.md' for 'wire.py' returns lines 54, 61 and 87 -- the minimal-first-version sentence, the container-boundary sentence, and the jail-type-agnostic sentence -- none of which says shared or duplicated; a grep for 'duplicat|shared|import' returns only line 39, about channel exclusivity. This matters because decision-0002 item 5 makes the wire shape the gate for starting Seatbelt ('Seatbelt can start as soon as the supervisor's wire *shape* is settled, since program.py/wire.py are meant to be jail-type-agnostic'): whoever picks that up reads the decision, not a draft's notes, and will find the question still open there. Secondary: DRAFT-0009 is still status Draft with 3/3 ACs ticked -- work graded against something never accepted onto the board.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 decision-0002's own text states the shared-on-the-host / duplicated-in-the-jail split and why rule 17 forces it
- [x] #2 DRAFT-0009's status reflects reality: promoted and closed, or its ACs re-opened
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Edit decision-0002's own text to state plainly: wire.py's message format is
   shared by import on the host side (link.py: `from brig.infra.supervisor import
   wire`) and duplicated by convention on the jail side (program.py assembles into
   a standalone stdlib-only file with no installed brig package to import from,
   rule 17) -- and why rule 17 forces that split. Land it near the existing
   wire.py mentions (lines ~54/61/87), not as a disconnected addendum.
2. DRAFT-0009's 3/3 ACs are genuinely met (already independently verified across
   this session's reviews) -- promote it to a task and close it via the normal
   review/close-task path, citing that existing evidence, rather than leaving it
   sitting as an accepted-in-substance Draft.

### Proof
- decision-0002's own text, read cold, answers "shared or duplicated" without
  needing to open DRAFT-0009's notes.
- DRAFT-0009 (promoted) closed via close-task, or its ACs explicitly reopened with
  a stated reason if review finds otherwise.

### Risks
- Low: pure documentation/bookkeeping, no code or test changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC#1: decision-0002 item 1 (near the existing wire.py/program.py/link.py assembly text, lines ~58-72) now states plainly that wire.py's message format is shared by import on the host side (link.py: 'from brig.infra.supervisor import wire', costing nothing since both modules are stdlib-only and same-package) and duplicated by convention on the jail side (program.py matches wire.py's message-kind/field names literally), and explains why: rule 17 requires wire.py+program.py to assemble into the one stdlib-only file dropped as PID 1 with no other import, so there is no installed brig package there for a qualified import to resolve against and no bare 'import wire' this file's own package location can produce. Rule 17 forces only the jail-side duplication; the host-side sharing is unconstrained by it and simply free. A matching clause was also added to item 5's Seatbelt-readiness sentence, since that is where the bug description says whoever picks up Seatbelt will actually look. AC#2: DRAFT-0009 promoted ('backlog draft promote DRAFT-0009' -> TASK-0010, no id collision with the pre-existing TASK-0009) and closed via close-task, citing its own already-settled evidence (teardown->effects edge, container-attribution sync, and the wire.py shared/duplicated split verified by 'just gates' pypeeker rule 6 and a manual link.py/program.py pipe round-trip) rather than re-deriving it; its 3/3 ACs held up on inspection, so nothing was reopened.

No repro: pure documentation/bookkeeping (decision-0002's own text, plus promoting and closing DRAFT-0009) with no code behavior to reproduce a failure against.

Check `uv run just done` exited 0

(194 earlier lines omitted)
```text
[2m14:46:23.144[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m14:46:23.144[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m14:46:23.144[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m14:46:23.145[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m14:46:23.149[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m14:46:23.422[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 285ms
[2m14:46:23.425[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m14:46:23.425[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 509ms[39m[0m

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
INFO    -  Documentation built in 1.67 seconds

== architecture validate: PASS ==
[2m14:46:24.394[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m14:46:24.398[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m14:46:24.408[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m14:46:24.408[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m14:46:24.529[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m14:46:24.615[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m14:46:24.615[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 222ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```
<!-- SECTION:NOTES:END -->
