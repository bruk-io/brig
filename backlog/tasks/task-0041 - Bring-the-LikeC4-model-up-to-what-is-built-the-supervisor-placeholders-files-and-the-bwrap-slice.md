---
id: TASK-0041
title: >-
  Bring the LikeC4 model up to what is built: the supervisor, placeholders,
  files and the bwrap slice
status: To Do
assignee: []
created_date: '2026-11-03T04:39:00Z'
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
- [ ] #1 No built component or relationship is tagged #planned, and every module under src/brig has a component (or is named in one) in the model
- [ ] #2 likec4 validate and c4lint are clean (uv run just done passes)
<!-- AC:END -->
