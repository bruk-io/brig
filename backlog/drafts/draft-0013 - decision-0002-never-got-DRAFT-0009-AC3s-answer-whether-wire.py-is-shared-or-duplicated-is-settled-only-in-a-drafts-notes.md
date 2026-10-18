---
id: DRAFT-0013
title: >-
  decision-0002 never got DRAFT-0009 AC#3's answer: whether wire.py is shared or
  duplicated is settled only in a draft's notes
status: Draft
assignee: []
created_date: '2026-10-18 08:08'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
DRAFT-0009 AC#3 reads: 'decision-0002 says explicitly whether wire.py is shared by the host end (link.py) or duplicated, consistent with rule 17.' It is ticked, and the substance was genuinely settled during TASK-0001.15 step 3 (shared by import on the host side -- link.py does 'from brig.infra.supervisor import wire'; duplicated by convention on the jail side, since program.py assembles into a standalone stdlib-only file with no installed brig package to import from). But that settlement lives only in DRAFT-0009's own Implementation Notes. Evidence: grep of 'backlog/decisions/decision-0002 - The-supervisor-request-channels-and-the-grading-skeleton-the-next-slices-shape.md' for 'wire.py' returns lines 54, 61 and 87 -- the minimal-first-version sentence, the container-boundary sentence, and the jail-type-agnostic sentence -- none of which says shared or duplicated; a grep for 'duplicat|shared|import' returns only line 39, about channel exclusivity. This matters because decision-0002 item 5 makes the wire shape the gate for starting Seatbelt ('Seatbelt can start as soon as the supervisor's wire *shape* is settled, since program.py/wire.py are meant to be jail-type-agnostic'): whoever picks that up reads the decision, not a draft's notes, and will find the question still open there. Secondary: DRAFT-0009 is still status Draft with 3/3 ACs ticked -- work graded against something never accepted onto the board.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 decision-0002's own text states the shared-on-the-host / duplicated-in-the-jail split and why rule 17 forces it
- [ ] #2 DRAFT-0009's status reflects reality: promoted and closed, or its ACs re-opened
<!-- AC:END -->
