---
id: TASK-0033
title: 'Gate gaps: planted violations the pypeeker rules do not catch'
status: To Do
assignee: []
created_date: '2026-11-02T17:23:00Z'
labels:
  - size-3
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. 30 violations planted in a scratch copy: the layer, slice and test-layer rules caught every crossing tried. These exited 0: `pytest.MonkeyPatch.context()` and `setattr(brig, ...)` in tests (rule: no patching); a fake dataclass in `tests/e2e`; `os.write(1|2, ...)` and `logging` in infra or presentation (rule 14, one writer); `list`/`dict` fields on a frozen domain dataclass (rule 8).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each planted violation above fails the gate, with a pypeeker rule test that plants it
<!-- AC:END -->
