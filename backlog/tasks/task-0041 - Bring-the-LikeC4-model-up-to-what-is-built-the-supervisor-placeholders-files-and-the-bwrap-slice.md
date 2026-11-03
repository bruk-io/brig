---
id: TASK-0041
title: >-
  Bring the LikeC4 model up to what is built: the supervisor, placeholders,
  files and the bwrap slice
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T04:39:00Z'
updated_date: '2026-11-03T04:46:00Z'
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
<!-- SECTION:NOTES:END -->
