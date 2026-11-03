---
id: TASK-0044
title: A failed create_bwrap_jail leaves a running jail nothing can destroy
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - brig
  - lifecycle
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (reasoned from code): in presentation/drivers/bwrap.py, once run(operations.create...) started the supervisor, _placeholders.attach or _namespace_fd_for can still raise (ChannelNamespaceNotFound is documented 'with process still running'). The except path unlinks the script, removes the channel directory and releases placeholders while the jail still mounts over them, and never tears the process down; the embedder gets no Jail to destroy. Proposed: once a process exists, the failure path runs operations.destroy and releases placeholders only on GONE; share one cleanup with destroy_jail.
<!-- SECTION:DESCRIPTION:END -->
