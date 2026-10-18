---
id: DRAFT-0013
title: >-
  Should decision-0001 rule 4's unit-test clause, and rule 6's
  no-reaching-into-_names rule, cover test-to-test imports the way the
  integration clause covers brig-package imports
status: Draft
assignee: []
created_date: '2026-10-18 13:30'
updated_date: '2026-10-18 20:43'
labels:
  - brig
  - size-1
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0009 added tests/unit/test_bwrap_compile.py importing a private constant (_BWRAP_ARGV_PREFIX) from tests/e2e/test_tiocsti_battery.py, to assert that e2e literal against compile_supervisor_launch's real output (a fidelity check the task's committed plan asked for). This is authorized by the plan and green under both pypeeker rules as currently implemented, but only because neither rule's checker reaches this case:

- brig-test-layers' unit-test part (pypeeker_rules/brig.py's _unit_test_violations) only flags imports where row.imported_from.is_within("brig") -- a bare tests.e2e... import never matches, so tests/unit is unrestricted in what it can import from other test modules. The integration-test part (_integration_test_violations) is stricter: it does restrict tests imports (requiring tests.integration.fakes). That asymmetry may be deliberate (unit tests are meant to be freer) or may be a gap nobody noticed because no unit test had reached into another test module before.
- decision-0001 rule 6 (no reaching into another module's _names) is stated as a house rule but its pypeeker implementation (under-exposed-access, from the brig-prefixed scope) does not appear to reach test-to-test imports either -- _BWRAP_ARGV_PREFIX is a private name of tests/e2e/test_tiocsti_battery.py, reached into from tests/unit/test_bwrap_compile.py, with no finding.

Open question: should rule 4's unit clause (and/or rule 6) be extended to cover tests-package imports the way the integration clause does, closing this gap for future cross-test-layer imports -- or is a unit test importing a private constant from an e2e test module (to check the e2e module's own fidelity, the exact shape TASK-0009 needed) something decision-0001 should explicitly bless as a named exception, documented rather than merely unchecked?

Not blocking: TASK-0009's own committed plan explicitly authorized a unit-or-integration-layer test here, so the import stands either way this is resolved.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Dropped, not pursued: a genuine but low-priority open question about whether decision-0001 rule 4's unit-test clause should cover test-to-test imports the way the integration clause covers brig-package imports. Self-assessed non-blocking when filed (TASK-0009's own committed plan already authorized the one import that prompted this, so nothing currently on the board depends on resolving it). Owner's call: drop rather than investigate further.
<!-- SECTION:NOTES:END -->
