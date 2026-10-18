---
id: DRAFT-0010
title: >-
  The supervised command's own stdin/stdout have nowhere to go: program.py's
  child inherits the wire pipes
status: Draft
assignee: []
created_date: '2026-10-18 04:34'
labels:
  - brig
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found empirically while building infra/supervisor/link.py (TASK-0001.15 step 3):
a manual end-to-end run of link.py's _start against the real program.py, with
the supervised command set to /bin/echo something, delivered the real
command's own stdout bytes to link.py's events pipe, where wire.decode_event
raised WireError on them -- not a started/exited/done line.

The cause is structural, not a bug in any one function. link.py's _start
connects the supervisor's own fd 0/1 to the request/events pipes (decision-0002's
wire protocol: "one exec request in... a stream of events out"), through
infra.processes.spawn's stdin_fd/stdout_fd. program.py's _start_child then
forks the real command with `os.posix_spawnp(argv[0], argv, env)` and no
file_actions of its own, so the real command inherits the supervisor's own
fd 0/1/2 as-is -- the same wire pipes, not a stream of its own. Concretely:
- The real command's stdout writes land in the *events* pipe, interleaved
  with (and indistinguishable from) the supervisor's own JSON lines.
- The real command's stdin reads from the *request* pipe, whose write end
  link.py already closed after sending the one exec request -- so the real
  command sees stdin closed (EOF) immediately, regardless of what the
  embedder's own jail API caller might have wanted to hand it.

Before the supervisor existed, the jailed command's own stdio were whatever
bwrap's own invocation gave it (ordinarily inherited from the embedder's
process). The supervisor sitting in between, as currently built, removes that
path entirely and does not replace it with anything -- decision-0002's
"minimal first version" names only started/exited/done, not the real
command's own I/O.

This is a design question, not an obvious bug fix: what should the
supervised command's stdin/stdout/stderr actually be wired to once a
supervisor is PID 1 inside the jail? Candidates include (not evaluated here):
giving program.py its own separate fds for the wire protocol (e.g. a second
pair of pipes at fixed fd numbers, set up by link.py the same way stdin/stdout
are now, read/written by program.py instead of fd 0/1) and leaving fd 0/1/2
free to inherit whatever the jail type's own driver arranges; or routing the
real command's output through the wire protocol itself as a new event kind.
Left to whoever designs the supervisor's fuller shape (decision-0002 already
defers the log envelope and egress to "after the supervisor lands" for a
similar reason).
<!-- SECTION:DESCRIPTION:END -->
