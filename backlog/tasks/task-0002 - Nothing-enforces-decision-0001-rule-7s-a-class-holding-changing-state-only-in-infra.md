---
id: TASK-0002
title: >-
  Nothing enforces decision-0001 rule 7's 'a class holding changing state only
  in infra/'
status: In Progress
assignee:
  - '@bruk'
created_date: '2026-10-17 22:57'
updated_date: '2026-10-18 04:33'
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
<!-- SECTION:NOTES:END -->
