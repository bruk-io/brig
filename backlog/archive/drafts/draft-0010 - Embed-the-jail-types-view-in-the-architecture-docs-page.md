---
id: DRAFT-0010
title: Embed the jail-types view in the architecture docs page
status: Draft
assignee: []
created_date: '2026-10-18 03:45'
labels: []
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
docs/architecture/views/brig/jail-types.c4 defines brigJailTypes, but docs/architecture/index.md renders only brigContext, brigContainers and brigLibraryComponents. The view that makes decision-0001 rule 3 (a jail type is a slice) visible is therefore in no built page, and the `docker` component (infra/docker.py, #paused) now appears in no view at all. Evidence: grep for 'likec4-view' in docs/architecture/index.md returns three blocks, none of them brigJailTypes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docs/architecture/index.md embeds brigJailTypes with prose saying what rule 3 the reader is looking at
- [ ] #2 The treatment of #paused components that appear in no view (docker) is stated, either by including it somewhere or by saying in prose why it is model-only
- [ ] #3 mkdocs --strict, likec4 validate and c4lint stay clean
<!-- AC:END -->
