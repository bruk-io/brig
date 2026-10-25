---
id: DRAFT-0011
title: >-
  StopIteration escapes the channel-readiness primitives where only OSError is
  caught
status: Draft
assignee: []
created_date: '2026-10-25 16:57'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-0001.27's review. Two places in src/brig/infra/sockets.py can raise StopIteration out of a function whose own contract says it never raises, because both catch OSError only and both read a /proc line with next(...):

1. channel_ready: pidfd_pid = next(int(line.split()[1]) for line in handle if line.startswith('Pid:')) over /proc/self/fdinfo/<pidfd>, inside a try whose only handler is 'except OSError: return ChannelRefused(PEER_LOOKUP_FAILED)'. The function's docstring states 'Every failure this function can reach is one of those three values, never a raise (decision-0005 item 5)' and names exactly one exception (the jail_namespace_fd readlink precondition). StopIteration is an unnamed second one.

2. jail_pid1_namespace: its scan loop catches OSError only, while _nspid uses next(...) over /proc/<pid>/status for the NSpid: line. _nspid's own docstring already specifies the intended behaviour -- 'a StopIteration (status carried no NSpid: line at all) ... mean[s] "this candidate is not the jail's PID 1", never "the scan is over"' -- and the code does not implement it: the StopIteration escapes the whole scan and reaches create_bwrap_jail untranslated.

Realistic path: _children's own docstring concedes a process can exit between the listdir and the read; a task read mid-exit can open status successfully and yield no NSpid: line, which raises StopIteration, not OSError. Same class as the ENOPROTOOPT/EINVAL misclassification fixed under TASK-0001.27: the docstring already specified the behaviour and the code did not implement it.

Does not breach TASK-0001.27 AC#4, whose enumeration is literally OSError.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 channel_ready returns ChannelRefused(PEER_LOOKUP_FAILED) rather than raising when /proc/self/fdinfo/<pidfd> carries no Pid: line, and a test pins it
- [ ] #2 jail_pid1_namespace skips a candidate whose status carries no NSpid: line and keeps scanning until its deadline, as _nspid's docstring already specifies, and a test pins it
<!-- AC:END -->
