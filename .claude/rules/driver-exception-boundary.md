---
paths:
  - "src/brig/presentation/drivers/**/*.py"
  - "src/brig/presentation/api.py"
---
# The driver exception boundary

Applies when writing or editing a presentation driver or the public API it wires into.

- A driver is the only code that calls `infra`, so it is the only code that catches an
  infra exception and raises one of `presentation/errors.py`'s own types in its place
  (decision-0001 rules 9 and 13). An embedder handles brig's own types without ever
  seeing `infra`'s.
- This has escaped untranslated twice already, in two separate adversarial reviews
  (TASK-0001.03, TASK-0001.06) - each time because a *new* effect or call site into
  `infra` was added without wrapping it, not because the rule was unknown. Checking it
  once when the driver was first written was not enough.
- When adding or touching any call from a driver into `infra`, grep every call site in
  that driver module for `infra.` and confirm each one is wrapped - not just the one
  the current change touches.
