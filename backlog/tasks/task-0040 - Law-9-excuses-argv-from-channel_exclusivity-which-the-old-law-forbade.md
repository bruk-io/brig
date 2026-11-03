---
id: TASK-0040
title: Law 9 excuses argv from channel_exclusivity, which the old law forbade
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T04:14:00Z'
updated_date: '2026-11-03T04:21:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
docs/spec/index.md law 9 (168a633): channel_exclusivity now grades only writable shared paths and socket places, and argv becomes the untested promise 'brig puts no secret there'. The old law (168a633^) said argv is counted in the enumeration and covered by the channel_exclusivity grade, never excused because the exposure is the host's. No cited test holds the argv clause.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Law 9 either counts argv in channel_exclusivity's enumeration as the old law did, or a decision records why it no longer does
- [x] #2 Law 9's argv clause names a test that holds it, or says none does yet
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03. Fixed at fe3f40d: law 9 again counts argv as one of the enumerated shared media, never excused because the exposure is the host's (the old law's words), says what brig's own argv carries (paths only) and that the environment and stdio travel by pipe and fd, and that nothing tests the argv count yet and the claim's grade does not include it.
<!-- SECTION:NOTES:END -->
