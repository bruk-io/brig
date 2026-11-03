---
id: decision-0006
title: >-
  The supervisor is non-dumpable and the jail holds no capabilities, so the
  supervised command cannot reach its PID 1
date: '2026-11-03T02:37:00Z'
status: accepted
---
## Context

TASK-0022: the supervised command is the direct child of the supervisor, which is PID 1 of the
jail's PID namespace, under the same uid, and the jail mounts its own procfs (decision-0004).
So the command reopened the supervisor's events pipe through `/proc/1/fd/<n>` and wrote a
`done` of its own: `run_jail` returned 42 after 0.05s while the real command still ran. It
could also `ptrace` PID 1 and open `/proc/1/mem` read-write. `program.py`'s fd closes do not
help: a same-uid child that can read `/proc` reaches its parent through it.

Measured 2026-11-03 (Linux 6.18, bubblewrap 0.9.0, Python 3.15.0b4), a stand-in PID 1
holding a pipe its child did not inherit, the child trying `/proc/1/fd/<n>` (write),
`/proc/1/environ`, `/proc/1/mem` and `ptrace(PTRACE_ATTACH, 1)`:

| caller | PID 1 | bwrap flags | command's CapEff | all four |
|---|---|---|---|---|
| root | dumpable | (as today) | `000001fffeffffff` | succeed |
| root | non-dumpable | (as today) | `000001fffeffffff` | succeed |
| root | dumpable | `--cap-drop ALL` | `0` | succeed |
| root | non-dumpable | `--cap-drop ALL` | `0` | refused |
| uid 1000 | dumpable | either | `0` | succeed |
| uid 1000 | non-dumpable | either | `0` | refused |

Two facts in that table. A non-dumpable process refuses `/proc/<pid>/{fd,environ,mem}` and
ptrace to a same-uid peer that lacks `CAP_SYS_PTRACE` in its user namespace. And bwrap run by
root keeps nearly every capability in the jail's user namespace (it drops none by default for
a privileged caller), so there `CAP_SYS_PTRACE` overrides the dumpable check, and the command
also holds `CAP_SYS_ADMIN` and the rest inside its namespaces.

Considered and not taken: a nested PID namespace for the command (its own procfs needs a
mount namespace and privilege inside the jail, and doubles the reaping), another uid (needs a
mapping bwrap does not give an unprivileged caller), authenticating the events channel
(the command could still ptrace the supervisor and forge from inside it).

## Decision

1. The supervisor makes itself non-dumpable (`prctl(PR_SET_DUMPABLE, 0)`) as the first thing
   it does, before it reads the exec request or starts the command, and refuses to run the
   command if the call fails. `ctypes` is the standard library, so rule 17 holds.
2. The bwrap compile adds `--cap-drop ALL` unconditionally, with the namespace flags: the jail
   holds no capability, whoever runs brig.
3. The command's own exec resets it to dumpable, which is what it should be: nothing in the
   jail protects the command from itself.
4. The host keeps its reach: it owns the jail's user namespace, so it holds every capability
   there and still reads the supervisor's `/proc/<pid>/ns/pid` (decision-0005).
5. An e2e battery plants the forgery, and opens PID 1's `environ` and `mem` from the command
   (the kernel's ptrace access check, which an attach makes too), with positive controls that
   the same probes succeed against a process of the command's own.

## Consequences

- `program.py`'s claim that the exit code is `waitpid`-authenticated becomes true: nothing in
  the jail can write the supervisor's wire.
- A jail run by root is no longer a root with capabilities inside its namespaces.
- Seatbelt's slice needs its own answer (macOS has no `PR_SET_DUMPABLE`; `PT_DENY_ATTACH`
  and the sandbox profile are the candidates), decided with that slice.
