---
id: TASK-0065
title: create_seatbelt_jail fails when BRIG_HOME is reached through a symlink
status: To Do
assignee: []
created_date: '2026-11-12 19:08'
labels:
  - darwin
dependencies: []
type: bug
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by bh-02 TASK-0196 (2026-11-12). If BRIG_HOME is reached through a symlink (for example /tmp rather than /private/tmp), create_seatbelt_jail raises JailMembersUnverifiable for a long-running command under a narrow policy, because resolved_state_dir does not realpath it. The default ~/.brig is unaffected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 create_seatbelt_jail works with BRIG_HOME under a symlinked path such as /tmp
- [ ] #2 A test covers the symlinked BRIG_HOME
<!-- AC:END -->
