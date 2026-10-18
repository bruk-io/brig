---
id: DRAFT-0002
title: >-
  Gate-rule scoping gap: over-exposed-module-symbol vs pytest's test-collection
  convention
status: Draft
assignee: []
created_date: '2026-10-17 21:53'
updated_date: '2026-10-18 17:44'
labels:
  - brig
  - gates
dependencies: []
parent_task_id: TASK-0001
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

TASK-0001.03's adversarial review found `just gates` failing on every test file: `over-exposed-module-symbol` flagged every pytest test function (public, used nowhere else in the repo by construction -- renaming them with a leading underscore would stop pytest collecting them) plus `FakeProcesses`.

TASK-0001.03 fixed this locally with a scoped exemption:

```toml
[tool.pypeeker.over-exposed-module-symbol]
allow = ["unit.*", "integration.*", "e2e.*"]
```

This holds `just done` green and does not touch `brig.*`, so the rule still polices the library's own code in full. But two things are worth a closer look by whoever owns the gates (TASK-0001.04's scaffolding did not cover this):

1. Is a blanket `allow` over the three test-layer module prefixes the right long-term shape, or should pypeeker's own rule understand pytest's collection convention (a configurable "test-function" exemption) instead of a per-project allow-list every brig-shaped project has to write out by hand?
2. `FakeProcesses` was flagged as "only used within its module" despite being imported by `tests/integration/test_walking_skeleton.py`. That is suspicious on its own (it IS used elsewhere) and may be the same dual-module-naming defect TASK-0001.03 had to fix for mypy (`tests/integration/fakes.py` resolving to two different dotted names -- `fakes` and `tests.integration.fakes` -- because `tests/` has no `__init__.py`). If pypeeker's own cross-reference resolution has the same blind spot, the `allow` exemption is papering over a real indexing bug rather than a true policy choice, and it is worth confirming before more fakes get added across more test files.

## Open questions

- [ ] Does pypeeker need a built-in pytest-aware exemption, or is the `allow` list the intended mechanism for this?
- [ ] Is `FakeProcesses`'s flagging explained by the same dual-module-naming defect mypy had, or something else in pypeeker's indexer?
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verified, both open questions answered -- archiving rather than promoting.

Q2 (indexer blind spot?): checked directly, today, with pypeeker symbol/refs
against the real index (7 real cross-file imports now exist, not the 1-2 that
existed at TASK-0001.03's time). `pypeeker symbol FakeProcesses` shows every
import correctly resolved via its fully-qualified dotted path
(tests.integration.fakes.FakeProcesses), across all 7 importing files, with no
dual-identity confusion -- unlike mypy's actual dual-module-naming defect
(tests/ having no __init__.py), pypeeker's own cross-reference resolution is
NOT confused here. `just gates` also shows zero findings for FakeProcesses
today. Whatever TASK-0001.03's review observed was a true snapshot of the
world at that moment (fewer cross-file imports existed yet), not a live
indexer bug -- nothing in brig needs fixing for this.

Q1 (should the allow-list be a native pypeeker feature instead?): a real
question, but about pypeeker itself, a separate project brig only depends on
-- not something brig's own board can resolve or needs to track. The current
allow-list (`[tool.pypeeker.over-exposed-module-symbol] allow = [...]`) holds
just gates green and doesn't touch brig.* itself, which is the property that
actually matters here. Worth raising with pypeeker's own maintainer separately,
outside this board.
<!-- SECTION:NOTES:END -->
