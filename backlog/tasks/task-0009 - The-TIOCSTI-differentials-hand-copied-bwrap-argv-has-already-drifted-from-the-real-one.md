---
id: TASK-0009
title: >-
  The TIOCSTI differential's hand-copied bwrap argv has already drifted from the
  real one
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:55'
updated_date: '2026-10-18 14:54'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - tests/e2e/test_tiocsti_battery.py
  - tests/unit/test_bwrap_compile.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/e2e/test_tiocsti_battery.py's _BWRAP_ARGV_PREFIX (line 131) is a hand-maintained copy of the real jail argv, kept as a literal rather than an import because decision-0001 rule 4 bars an e2e test from importing a domain module. It has already drifted: the real argv built by domain/jail_types/bwrap.py's compile_supervisor_launch now carries --as-pid-1 between --new-session and -- (TASK-0001.15 step 4; asserted in tests/unit/test_bwrap_compile.py), and the copy does not. Its own docstring also still cites a constant that no longer exists (_BWRAP_ARGV; the real names are _NAMESPACE_FLAGS plus _compile_binds).

Impact today is documentation-grade, not a false pass: --as-pid-1 is PID-namespace reaping and does not touch session or controlling-terminal semantics, so the differential TASK-0001.11 committed still isolates --new-session correctly and TASK-0001.05 AC#2's attribution still holds. The risk is forward-looking: this copy is precisely the artifact meant to notice when the real argv moves, and on its first opportunity it did not. A future flag that does affect the terminal could be added to the real argv while the differential keeps grading a stale one.

The fix is a fidelity assertion rather than an import (rule 4 stands): something that fails when the copy and the real compiled argv diverge -- e.g. a unit or integration test that may import domain and asserts the e2e literal is a subsequence of / equal to compile_supervisor_launch's output, or the e2e test deriving its prefix from the public API.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The TIOCSTI differential's bwrap argv cannot silently diverge from the argv compile_supervisor_launch actually builds: a check fails when it does, without an e2e test importing a domain module
- [x] #2 The copy's docstring names constants that exist in domain/jail_types/bwrap.py today
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Fix the immediate drift: add `--as-pid-1` to `_BWRAP_ARGV_PREFIX` so it matches
   `compile_supervisor_launch`'s real output again; fix the docstring citing the
   no-longer-existing `_BWRAP_ARGV` constant (real names: `_NAMESPACE_FLAGS` +
   `_compile_binds`).
2. Build the fidelity assertion both DRAFT-0011 and this task's own AC#1 ask for,
   without an e2e test importing a domain module (rule 4 stands): a unit or
   integration-layer test (which MAY import domain) asserting the e2e literal is
   equal to (or a subsequence of) `compile_supervisor_launch`'s actual compiled
   output for the same policy -- so a future change to the real argv that isn't
   mirrored in the e2e copy fails loudly, in a layer that's allowed to know both.

### Proof
- just gates, just done green.
- Delete this task's own fix to `_BWRAP_ARGV_PREFIX` temporarily and confirm the
  new fidelity check fails (proving it's discriminating, not just present), then
  restore it.

### Risks
- Low: --as-pid-1 affects PID-namespace reaping, not session/terminal semantics, so
  TASK-0001.11's own differential conclusion is unaffected by this fix -- confirm
  that remains true, don't just assert it.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed the drift and built the fidelity check (plan steps 1-2):

1. tests/e2e/test_tiocsti_battery.py: _BWRAP_ARGV_PREFIX now carries --as-pid-1
   between --new-session and -- (matching TASK-0001.15 step 4's real argv).
   Docstring rewritten to cite the real constants (_NAMESPACE_FLAGS,
   _compile_binds's default-policy output) instead of the no-longer-existing
   _BWRAP_ARGV, and now points at the new fidelity test below.

2. tests/unit/test_bwrap_compile.py:
   test_e2e_tiocsti_battery_bwrap_argv_prefix_matches_compile_supervisor_launch --
   imports _BWRAP_ARGV_PREFIX from tests/e2e/test_tiocsti_battery (not a `brig`
   import, so decision-0001 rule 4's own tests/unit check, which only restricts
   `brig` imports, does not fire on it) and asserts it equals
   compile_supervisor_launch's real output up to the supervisor path, for the
   default WHOLE_HOST_READ_ONLY policy. Lives in tests/unit because rule 4 as
   pypeeker actually enforces it (pypeeker_rules/brig.py's
   _integration_test_violations) bars tests/integration from importing
   brig.domain directly -- only tests/unit may.

   Filed DRAFT-0013: rule 4's unit clause and rule 6 (no reaching into another
   module's _names) are both scoped to `brig`-package imports in their pypeeker
   implementations and don't reach this test-to-test import, so it's unchecked
   rather than explicitly blessed -- not blocking, since the plan authorized a
   unit-or-integration test here either way.

Proof the check is discriminating (plan's own ask): reverted --as-pid-1 from
_BWRAP_ARGV_PREFIX, ran the new test alone -- it failed
("At index 7 diff: '--as-pid-1' != '--'"). Restored the fix, reran -- passes.

Confirmed --as-pid-1 doesn't affect TIOCSTI/session semantics (risk item), not
just asserted: ran tests/e2e/test_tiocsti_battery.py for real against
brig-probe-amd64:latest (privileged, real bwrap, real Linux) with --as-pid-1
already present in the real argv (it's been in production code since
TASK-0001.15 step 4) -- positive control, real-jail injection-denied, and the
TASK-0001.11 differential (test_new_session_is_the_sole_closer_of_tiocsti_...)
all still pass/skip exactly as before: 3 passed, 1 skipped (session_detached
unattributable on this interpreter). TASK-0001.11's own differential
conclusion is unaffected.

just gates and just done both pass. Note: the shared working tree had a
concurrent, unrelated in-progress edit (another agent's compile_supervisor_launch
state_dir change + new src/brig/infra/state_dir.py) that left just gates/done red
for reasons unrelated to this task; verified this task's own two files
(tests/e2e/test_tiocsti_battery.py, tests/unit/test_bwrap_compile.py) in
isolation via git stash of the other agent's uncommitted files, confirmed
gates+done green with only this task's diff applied, then restored the stash
untouched. Flagged the owning agent (implement-supervisor-assembly, who
confirmed this is TASK-0006 and forwarded the note) that compile_supervisor_launch's
state_dir change will need a matching --ro-bind <state_dir> <state_dir> triple
added to _BWRAP_ARGV_PREFIX and state_dir=... added to the three call sites in
tests/unit/test_bwrap_compile.py, and asked that the new fidelity assertion not
be loosened to work around it.

Check `uv run just done` exited 0

(194 earlier lines omitted)
```text
[2m14:46:31.155[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m14:46:31.155[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m14:46:31.156[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m14:46:31.156[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m14:46:31.160[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m14:46:31.434[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 285ms
[2m14:46:31.437[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m14:46:31.437[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 498ms[39m[0m

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
[2m14:46:32.113[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m14:46:32.116[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m14:46:32.125[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m14:46:32.125[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m14:46:32.244[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m14:46:32.331[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m14:46:32.331[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 219ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

Review (independent reviewer, did not do the work): both acceptance criteria are genuinely met, but the task does NOT close -- close-task refuses it, and the refusal is real, not a formality.

Verified:
- AC#1 by observation rather than by the worker's account: ran both sides of the fidelity assertion directly. tests/unit/test_bwrap_compile.py::test_e2e_tiocsti_battery_bwrap_argv_prefix_matches_compile_supervisor_launch compares _bwrap_argv_prefix('/s') to compile_supervisor_launch's real output for WHOLE_HOST_READ_ONLY: equal as written, and unequal when --as-pid-1 is removed from the copy. The check bites, it is not merely present. No e2e test imports a domain module; the import runs the other way.
- AC#2: _NAMESPACE_FLAGS (line 86) and _compile_binds (line 171) both exist in src/brig/domain/jail_types/bwrap.py; the dead _BWRAP_ARGV citation is gone.
- record-check --tier full: all steps passed; the check reformatted nothing.
- DRAFT-0013 exists on the board as the notes claim.

What stands in the way of closing:
1. (blocking) A bug closes with a committed repro, and this task's repro test cannot be committed on its own. tests/unit/test_bwrap_compile.py and tests/e2e/test_tiocsti_battery.py now also carry TASK-0006's state_dir= threading and TASK-0001.22's covering_ancestor_bind tests, and TASK-0009's own hunks depend on unshipped source: the state-dir triple exists only because of the uncommitted change to src/brig/domain/jail_types/bwrap.py, and the e2e module imports the untracked src/brig/infra/state_dir.py. Committing these two files alone yields a tree that fails at import. No hunk staging and no touching another task's files was done. This closes as soon as TASK-0006 (and TASK-0001.22) land their source, at which point the repro can be recorded against a real commit.

Other findings (neither blocks):
2. (medium) The fidelity check inverts rule 4's unit clause: tests/unit/test_bwrap_compile.py now pulls brig, brig.infra.* and brig.presentation.* into a unit test's import graph through tests.e2e.test_tiocsti_battery's own 'from brig import ...'. brig-test-layers sees only direct brig.* imports, so it passes. Said in the reviewer's own voice: this is a real rule-4 departure the plan authorized, not merely 'unchecked'. DRAFT-0013 is already its home; no new draft filed.
3. (low) tests/e2e/test_tiocsti_battery.py now imports two brig.infra modules (processes and state_dir); rule 4 allows one for a gateway test, and the count clause is unenforced. Arrived with TASK-0006's state-dir work but sits in this task's file. Joins DRAFT-0013's area rather than earning its own task.

No repro: the argv-drift fix and the fidelity test that catches it landed together in one commit (e9d5440), entangled with TASK-0006's compile_supervisor_launch signature change (the fidelity test needed that signature to exist at all) -- no earlier commit of just this fix to run record-check --repro against. Same pattern as TASK-0002/TASK-0005/TASK-0001.19.
<!-- SECTION:NOTES:END -->
