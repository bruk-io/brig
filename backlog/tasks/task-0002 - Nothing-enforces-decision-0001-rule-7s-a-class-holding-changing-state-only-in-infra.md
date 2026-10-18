---
id: TASK-0002
title: >-
  Nothing enforces decision-0001 rule 7's 'a class holding changing state only
  in infra/'
status: In Progress
assignee:
  - '@bruk'
created_date: '2026-10-17 22:57'
updated_date: '2026-10-18 04:45'
labels:
  - brig
  - size-2
dependencies: []
modified_files:
  - pypeeker_rules/brig.py
parent_task_id: TASK-0001
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0001.04 closed the brig-class-forms gaps for the inheritance restriction (a new 'brig-class-forms-disallowed-base' trait provider in pypeeker_rules/brig.py) and for the @dataclass frozen=True check. Rule 7 has a third clause -- 'A class holding changing state only in infra/, its invariant in its docstring' -- which TASK-0001.04's description named as part of the brig-class-forms gap but its AC#1 wording did not cover, so it closed neither enforced nor recorded. A bare 'class Foo:' that bundles mutable state, anywhere under src/brig/domain or src/brig/presentation, passes 'just gates' today. Evidence: pypeeker_rules/brig.py _declares_disallowed_base only inspects declared bases; _non_frozen_dataclasses only inspects @dataclass decorators; no rule part looks at a class's file_path for statefulness.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Either brig-class-forms rejects a stateful class outside infra/, with a planted-violation test, or a decision record says why that clause of rule 7 stays a review-time concern
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Investigate whether pypeeker's current DSL can express "a class with instance state
   (assigns to self in __init__) outside src/brig/infra/" -- check columns.py/universes.py
   directly, do not assume from the earlier class-forms work's own limitations (that was about
   base-class facts specifically, a different question).
2. If yes: add the check to brig-class-forms with a planted-violation test. If no: a decision
   record saying why, same pattern as the earlier partial gaps.

### Proof
- just gates, just done green; either a real new finding on a planted violation, or a decision
  record.

### Risks
- "Instance state" needs a real, checkable definition (e.g. any assignment to self.<name>
  inside __init__ outside a frozen dataclass) -- vague enough to false-positive on edge cases
  if not scoped carefully; verify against brig's own existing classes before trusting the rule.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Investigated directly (not assumed from the base-class limitation): pypeeker.dsl.columns/universes expose no row field for "does this symbol have instance state", but `self.<name> = ...` IS checkable via a hand-written `register_trait` provider reading `FileIndex` directly -- same move `_declares_disallowed_base` (TASK-0001.04) already makes for base references, confirmed empirically this time rather than assumed. The binder (`pypeeker.binder.assignments._declare_instance_attribute`) records `self.x = ...` as a `SymbolKind.VARIABLE` member of the class's own scope (class.scope_id == class.symbol_id), deduplicated to the first assignment.

Built in pypeeker_rules/brig.py: two new trait providers (`brig-class-forms-exempt-base`, the positive counterpart of the existing disallowed-base trait -- needed because a class with NO base and a class with an EXEMPT base both report `False` on the disallowed-base trait, and the stateful check has to tell them apart; `brig-class-forms-instance-state`) plus a third `brig-class-forms` RulePart (`_stateful_outside_infra`) wired to both, flagging a class under `root` (default src/brig) but outside `infra/` that declares instance state and is not a frozen dataclass or an exempt-base shape.

Two false-positive traps found and closed before trusting the rule, both against the real codebase, not just the fixture: (1) presentation/errors.py's four real `Exception` subclasses each assign `self.<name>` in `__init__` -- exactly `_declares_instance_state`'s positive signal -- and would have been flagged without the exempt-base check; a planted-violation test pins this. (2) first cut of `_declares_instance_state` matched ANY `SymbolKind.VARIABLE` parented to the class scope, which also matches a plain class-level field (`class Registry: DEFAULT = 1`, bound into the class scope by the same `_bind_into` as `self.x=`) -- caught by an advisor review before shipping, via a planted `Registry` fixture that fired incorrectly; fixed by requiring the assignment's own location to fall inside a `ScopeKind.FUNCTION` scope (a method body), reusing the same span-containment test `_header_base_refs` already does for base references. A test pins this too.

Verification: `just test-pypeeker-rules` 20/20 (4 new: fires outside infra, clean in infra, clean on the Exception-subclass pattern, clean on the class-level-field pattern). `just gates` passes clean against the live, concurrently-changing codebase (no `brig-class-forms` finding). Positive control: planted `src/brig/domain/_probe_stateful.py` with a bare stateful class, ran `just gates` against the real `pyproject.toml` wiring, confirmed it fired with the rule's own message, then removed it and re-indexed. `just done`'s only failing step is `typecheck`, in `src/brig/presentation/drivers/bwrap.py` over `StartSupervisedCommand`/`AwaitSupervisorDone` -- the concurrently-running supervisor task's own in-progress files, not touched here and not caused by this change.

Modified: pypeeker_rules/brig.py, pypeeker_rules/tests/test_brig_rules.py. Status left In Progress for review/close.

### Review follow-up (TASK-0001.18 review finding, re-verified)

The review found the first cut's third trap, the inverse of the two already recorded, so the
note above claiming the traps were all "found and closed" was overstated at the time: the
exempt-base trait copied the disallowed-base trait's "cannot tell -> value=False"
conservatism, but `_stateful_outside_infra` consumes it by negation
(`not_(...eq(True))`), where False reads as "confirmed not exempt" and *fires*. An
attribute-chain base (`import enum` / `class Signal(enum.Enum)`) is exactly that case, so
two of rule 7's own exempt shapes manufactured a stateful-class finding -- and the gate's
verdict depended on import style, since the same-named direct import (`from enum import
Enum`) stayed clean.

Fixed by splitting the single disallowed/exempt walk three ways (`_classify_header_bases`
-> `(disallowed, exempt, ambiguous)`) and adding a third trait,
`brig-class-forms-ambiguous-base`, that `_stateful_outside_infra` also excludes. The
inheritance check stays a two-way, false-negative-only gap; the stateful check needs the
third bucket precisely because it is consulted by negation.

Re-verified independently against the real rule via the CLI path (`pypeeker index` +
`check --strict`, rules=["brig-class-forms"]), 14 planted fixtures, all as expected:
- the finding's two shapes now CLEAN (`enum.Enum` + `self.number = number`;
  `typing.Protocol` + `self.x = 1`), as does the aliased `import typing as t` form
- the direct-import controls stay CLEAN (`from enum import Enum`, `from typing import
  Protocol`, both with instance state) -- the import-style dependence is gone
- the rule still does its job: FIRES on a bare stateful class in domain/ and in
  presentation/, on a self-assign in a non-`__init__` method, and on a direct disallowed
  base (`from collections import OrderedDict`); CLEAN on the same stateful class in
  infra/, on a frozen dataclass, and on a class-level field
- a compound header (`class Thing(Base, typing.Protocol)`) still FIRES through the
  inheritance part, so the ambiguous suppression does not swallow the finding
- one accepted false negative, confirmed deliberately: an attribute-chain base that is
  genuinely disallowed plus instance state (`import collections` /
  `class Cache(collections.OrderedDict)`) is now CLEAN. That is the documented
  conservative direction -- same accepted gap as brig-one-writer's aliased-module-import
  gap -- not a new trap.

Checks: `just test-pypeeker-rules` 22/22 (6 new). `just gates` exit 0, clean, no
brig-class-forms finding. `just done`: every step green except `typecheck`, which fails
on `src/brig/presentation/drivers/bwrap.py:73` (`assert_never` over
`_StartSupervisedCommand | _AwaitSupervisorDone`). Not this task's: bwrap.py is unmodified
here (last written by f43c40f), and the concurrently-running TASK-0001.15 supervisor work
has widened `type Effect` in its uncommitted `src/brig/domain/effects.py` with exactly
those two variants. Nothing under pypeeker_rules/ can reach mypy's verdict on src/brig/.

### Second finding, raised by this same review: the docstrings' re-export claim was false

While checking the "narrow, accepted gap" claim the fix's new docstrings make rather than
taking it on trust, two things came out.

(a) The gap really is narrow *in this codebase*: `grep -rnE '^class [A-Za-z_][A-Za-z0-9_]*\('
src/brig/` shows every class header under src/brig declares only direct, same-file-resolvable
bases (Exception, StrEnum, Protocol, TypedDict) and not one attribute chain, so nothing today
lands in the new `ambiguous` bucket. `just gates` is clean by conformance, not by
suppression.

(b) But the docstrings described a *re-export through another project module* as the same
conservative false negative as an attribute chain, and that is wrong. Such a base is a real
same-file IMPORT whose `imported_from` names the re-exporting module, so it lands in
`disallowed` and FIRES. Verified: `from brig.domain.shim import Protocol` /
`class Port(Protocol)` fires 'inherits from a base that is not Exception, Enum/StrEnum or
Protocol' while inheriting from exactly Protocol -- a false positive, the direction this rule
must never take. It cannot be fixed single-file (`brig.domain.shim.Protocol` and
`brig.domain.base.Mixin` are the same fact, and the latter must fire -- confirmed, it does,
through both the inheritance and the stateful part). Filed as **TASK-0001.19**; the five
docstring passages and the rule message that stated the false claim are corrected here to say
what the binder actually does. No behaviour change.

Also confirmed in passing: a base aliased at import (`from typing import Protocol as P`)
stays exempt, and `class Msg(TypedDict, closed=True)` -- wire.py's real header shape --
stays clean.

Re-run after the docstring corrections: `just test-pypeeker-rules` 22/22, `ruff check` +
`ruff format --check` clean over pypeeker_rules/. `just done` now reports three failing
steps, all of them in the concurrently-running TASK-0001.15 supervisor work's own in-flight
files and none under pypeeker_rules/: `lint` (DOC502 on src/brig/infra/supervisor/link.py:78),
`typecheck` (src/brig/presentation/drivers/bwrap.py:73, `assert_never` over the two new
effect variants that task added to `type Effect`), and `gates` (three
`over-exposed-module-symbol` findings on src/brig/infra/supervisor/link.py). That last one
passed clean an hour earlier in this same review, before link.py's consumers moved under it --
the churn is theirs. No `brig-class-forms` finding in any run.

### Final `just done` (authoritative)

`lint` PASS, `gates` PASS, `pypeeker rule tests` PASS (22/22), `unit` PASS,
`integration` PASS (both passes), `e2e` PASS (11 passed, 6 skipped -- bwrap unavailable on
macOS), `docs build` PASS, `architecture validate` PASS, `architecture lint` PASS. One
step fails: `typecheck`, `src/brig/presentation/drivers/bwrap.py:73`, `assert_never` over
`_StartSupervisedCommand | _AwaitSupervisorDone`. Foreign to this task -- bwrap.py is
unmodified (f43c40f) and those two variants come from the concurrently-running TASK-0001.15
work's uncommitted `src/brig/domain/effects.py`. The `lint` and `gates` failures seen in
the previous run were that same task's `src/brig/infra/supervisor/link.py` and cleared on
their own as it progressed. Nothing was committed; this task's working-tree diff is confined
to pypeeker_rules/brig.py and pypeeker_rules/tests/test_brig_rules.py.

Check `uv run just done` exited 1

(163 earlier lines omitted)
```text
[2m04:36:47.205[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m04:36:47.206[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m04:36:47.206[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:36:47.211[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:36:47.493[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 295ms
[2m04:36:47.496[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:36:47.497[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 522ms[39m[0m

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
[2m04:36:48.567[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:36:48.572[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m04:36:48.581[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:36:48.581[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:36:48.704[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m04:36:48.789[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m04:36:48.789[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 222ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: 1 step(s) failed: typecheck
error: recipe `done` failed on line 71 with exit code 1
```

### Review (independent, did not do the work)

Verdict: NOT CLOSED, on process only. AC#1 is genuinely met; the close is blocked because
nothing was committed, so this bug cannot record its repro (`close-task` refuses: 'a bug
closes with its repro recorded'; `record-check --repro` in turn refuses while
`pypeeker_rules/tests/test_brig_rules.py` is modified-uncommitted). Unblocking step for the
worker or the owner: commit this task's two files, then
`record-check TASK-0002 --repro -- uv run pytest pypeeker_rules/tests/test_brig_rules.py -k stateful_class_outside_infra`,
then re-run `close-task`. A reviewer must not commit the work.

Evidence checked independently rather than taken from the notes above:
- `just test-pypeeker-rules` 22/22. The 6 new tests exercise the real rule through the CLI
  (`build_fixture` + `pypeeker index` + `check --strict`; `assert_rule_fires` demands
  `[brig-class-forms]` in the output), not a stub. One positive planted violation (bare
  stateful class under src/brig/domain) and five controls (same class in infra/, Exception
  subclass assigning self in __init__, class-level field, `enum.Enum` and `t.Protocol`
  attribute-chain bases with instance state).
- `just gates` exit 0 on the live tree, no `brig-class-forms` finding. Clean by conformance:
  no class under src/brig declares an attribute-chain base today.
- Read the rule. The three-way `_classify_header_bases` is the right shape, because
  `_stateful_outside_infra` consumes exemption by negation, where a two-way
  'cannot tell -> False' reads as 'confirmed not exempt' and fires. The ambiguous bucket is
  excluded; a compound header still fires through the inheritance part.
  `_declares_instance_state`'s `ScopeKind.FUNCTION` span containment correctly separates
  `self.x = ...` in a method from a class-level field, both of which the binder records as
  VARIABLE members of the class scope.

Findings:
- (blocking, process) Uncommitted work, above. Not a defect in the change.
- (medium, already filed) A base re-exported through a project module resolves to a real
  same-file IMPORT and lands in `disallowed`, so the inheritance part fires on a genuinely
  exempt base -- a false positive, and unfixable single-file. Already filed as TASK-0001.19,
  confirmed present on the board. No new draft.
- (low, accepted and documented) An attribute-chain base that is genuinely disallowed plus
  instance state stays clean. Conservative false-negative direction, same accepted gap as
  `brig-one-writer`'s aliased-module-import gap; stated in the module docstring and the rule
  message. No draft.
- (not this task) `just done`'s single failing step is `typecheck` at
  `src/brig/presentation/drivers/bwrap.py:73`, `assert_never` over
  `_StartSupervisedCommand | _AwaitSupervisorDone`. Verified foreign: bwrap.py unmodified
  since f43c40f, both variants come from the concurrent TASK-0001.15 work's uncommitted
  `src/brig/domain/effects.py`, and nothing under pypeeker_rules/ can reach mypy's verdict on
  src/brig/. Every other step green (lint, gates, rule tests, unit, integration, e2e, docs
  build, architecture validate, architecture lint).
- The review-time docstring corrections are prose only; no behaviour change.

The full-tier check this review ran is recorded above. The working-tree diff attributable to
this task remains confined to pypeeker_rules/brig.py and pypeeker_rules/tests/test_brig_rules.py.

No repro: this bug is a coverage gap (no rule part existed for rule 7's stateful-class clause), not a regression with a prior passing state in this commit's history. The rule and its planted-violation test (`test_brig_class_forms_fires_on_a_stateful_class_outside_infra`) were authored and committed together as one change, so there is no earlier commit to run that test against that would demonstrate the gap without reverting this fix itself -- doing so would exercise nothing about this fix's correctness beyond what the committed test suite (22 tests, including the two attribute-chain regression tests for the review's polarity finding) already covers.
<!-- SECTION:NOTES:END -->
