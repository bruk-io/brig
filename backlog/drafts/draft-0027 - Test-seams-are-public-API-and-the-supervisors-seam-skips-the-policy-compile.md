---
id: DRAFT-0027
title: Test seams are public API, and the supervisors seam skips the policy compile
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T13:30:00Z'
labels:
  - brig
  - api
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: create_bwrap_jail(supervisors=...) skips the compile and reports frozendict(); the bwrap argv lives in LiveSupervisor, not the effect, so a structurally matching port runs the bare command. Rule 4 forces every fake seam into embedder signatures, while files, state_dir, placeholders and assemble have none. Also: Jail keeps the int of a namespace fd destroy_jail closed (a reused number would verify against another jail); destroy_jail takes the default directories port; 57 public names, 19 unrelated error classes, ValueError outside errors.py; no create-and-always-destroy helper; spec/glossary lines that do not match the code (compile_run, grade as only producer). Proposed: the launch argv on the effect (decision-0007 item 6), a host-facts port, a brig.testing entry, a stateful fd handle, a BrigError base.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03 (TASK-0045's review): Jail now holds two raw fd ints that destroy_jail closes, channel_namespace_fd and channel_directory_fd; both want the stateful handle that refuses use after close.

2026-11-04 (TASK-0001.36's review): create_bwrap_jail's egress_hosts is a test seam (a resolver override) in the public API; it lets an embedder point a granted name at any address. Every address is still judged by decide_egress, so it is no bypass, but it belongs with this draft's brig.testing / host-facts move.

2026-11-04 (TASK-0001.37's review): with a caller's own supervisors plus an EgressPolicy no proxy starts; the command then fails closed only because the proxy variables point at an unbridged 127.0.0.1:3128, a side effect rather than a guarantee. Moving the seams out of the public API ends it.

Design review 2026-11-04: too broad as one question, and its counts are stale (86 public names, 32 error classes). Confirmed hazard: StartSupervisedCommand.argv is the bare command, so a caller's own supervisors skips the compile. Pieces: (1) the launch as a value on the effect, argv plus named fd slots the driver fills (decision-0007 item 6), size 3, first: DRAFT-0025's bind fds and DRAFT-0028's listener fds need the same shape; (2) brig.testing, a host-facts port, egress_hosts moved there, amending decision-0001 rules 4 and 5, needs a decision, size 5; (3) an fd handle that refuses use after close, size 2; (4) a BrigError base, which breaks rule 7 unless amended, or a BRIG_ERRORS tuple, plus the six stray ValueError sites, size 2; (5) a create-and-always-destroy context manager, size 1-2; (6) spec and glossary (grade is not the only report producer), size 1. Recommended first decision record of the four: (1) and (2), narrowed.

2026-11-04 (TASK-0049's review): EgressLimits (create_bwrap_jail(egress_limits=...)) can only lower a limit, so it is a fair embedder knob, but its docstring presents it as a way for tests to lower them; with PolicyEgressLimitOutOfRange it belongs in this draft's public-API review. A fractional connections value passes the check and is truncated by int() in the program (0.5 becomes a cap of 0: stricter only).
<!-- SECTION:NOTES:END -->
