---
id: DRAFT-0010
title: >-
  The supervised command's own stdin/stdout have nowhere to go: program.py's
  child inherits the wire pipes
status: Draft
assignee: []
created_date: '2026-10-18 04:34'
updated_date: '2026-10-18 07:28'
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

## TASK-0001.15 step 4 update: confirmed regression, measured against real bwrap

Wiring presentation through the supervised path (StartSupervisedCommand/
AwaitSupervisorDone replacing Spawn/Reap for the normal create/run journey)
surfaces a concrete consequence of this gap, measured against real bwrap in a
privileged Docker container (ubuntu:24.04): `tests/e2e/test_tiocsti_battery.py`'s
`test_tiocsti_injection_fails_in_a_real_bwrap_jail` now fails --
`assert 125 == (100 + 1)`. Exit code 125 decodes (the battery's own
`_ERRNO_EXIT_OFFSET` of 100) to errno 25, `ENOTTY`: the probe's
`fcntl.ioctl(0, termios.TIOCSTI, ...)` now runs against fd 0 of the
*supervised* probe process, which is the exec request pipe (already closed on
its write end), not a controlling terminal at all -- so the ioctl fails for a
reason unrelated to confinement, and the battery can no longer tell "TIOCSTI
denied by the jail" apart from "TIOCSTI not applicable because fd 0 is not a
tty any more". TIOCSTI is, incidentally, still closed either way, but the
battery's own claim (AC#2/AC#3's attribution) is no longer evidence of that --
it is exactly the ambiguity rule 11's own batteries exist to avoid. This is
not a new bug introduced by the wiring step; it's the first concrete,
measured case of this already-filed gap actually breaking an existing
battery, now that the supervised path is live on the normal create/run
journey rather than only reachable by hand. Left unfixed here, same as
before: resolving it means designing the supervised command's own stdio
channel, which this draft already scopes as its own design question.

Separately confirmed in the same session: decision-0002's "a supervisor is
PID 1 inside the jail's namespace" needs bwrap's own `--as-pid-1` flag to
actually hold -- without it, `--unshare-all`'s implied `--unshare-pid`
installs bwrap's *own* reaper as the namespace's real PID 1, with the
supervisor running as PID 2 instead (measured: the supervisor's own `started`
event named a pid of 3, not 1, until `--as-pid-1` was added to
`domain/jail_types/bwrap.py`'s `_BWRAP_ARGV`). Fixed as part of this step,
unrelated to this draft's own stdio question, but recorded here since both
were found by the same real-bwrap measurement pass.

## TASK-0001.15 step 5 update: the same gap reaches test_claims_wiring.py's own grading, and the battery's own skip

Re-measured in a fresh `--privileged ubuntu:24.04` Docker container while writing step 5's tests: `test_tiocsti_battery.py::test_tiocsti_injection_fails_in_a_real_bwrap_jail` reproduces exactly as the update above describes (`ENOTTY`). Rather than leave it failing, it now skips with that measured reason (checked against the actual exit code, not unconditionally, so it starts asserting the real claim again on its own once this draft's stdio question is settled -- no code change needed there when that day comes).

A second, previously unrecorded consequence of the same root cause: `test_claims_wiring.py`'s `_measure_tiocsti_closure` drives the identical real-jail probe (`_jailed_tiocsti_probe`, through `create_bwrap_jail`/`run_jail`) to produce `Evidence` for the `tiocsti_closure` claim. On real Linux now, that probe also reports the `ENOTTY` exit code instead of 0 or the denied-errno shape, which `_evidence_from_measured_exit_codes` already classifies as the generic "ambiguous, no evidence" branch (`control_observed=False`) -- so `test_tiocsti_closure_claim_grades_from_whatever_this_host_can_measure` still passes, but the claim itself now grades `UNENFORCED` on Linux where it previously graded `ENFORCED`, through no code change and no test failure. No separate fix needed (the classifier's own existing honesty already absorbs it correctly), but it is a second, real-world consequence of this draft's own open question, beyond the one battery already named -- recorded here so whoever settles the stdio design question knows both call sites it will restore.

## Adversarial review update: this was a control-channel authentication hole, not only a stdio-ergonomics question

Two independent adversarial reviews of TASK-0001.15/.16/.17 (filed against this draft's own "program.py's child inherits the wire pipes" framing) measured the sharper consequence this draft's earlier text did not name: the supervised command inheriting the supervisor's own fd 1 is not only "its stdout corrupts our event stream" -- it is the supervised command being able to *write* `started`/`exited`/`done` lines onto the exact channel the host trusts for them. Measured through the public API against real bwrap: a jailed command that writes `{"kind": "done", "exit_code": 0}\n` to its own stdout and then sleeps 30-45s made `run_jail` return the fabricated exit code `0` after ~0.02-0.03s, while the real command kept running; `LiveSupervisors.await_done` then closed and forgot that pid, so the host could never learn the truth afterward. Pre-supervisor, the exit code came from `waitpid(2)` -- kernel-authenticated, unforgeable by the confined process. Post-supervisor, until this was fixed, it came from a byte stream the confined process could write to: the exact confused-deputy class decision-0002 cites old SPEC decision-185 for, reintroduced at the control channel itself, and reachable by grading (a claim could grade `ENFORCED` from an exit code its own measured subject authored).

**Fixed, separately from this draft's own open question**: `program.py`'s `_start_child` now gives the supervised command its own fd 0 and fd 1 -- each the one end of a pipe this function opens and immediately seals shut on the *other* end -- through `file_actions` on the `posix_spawnp` call, so a read from fd 0 sees EOF immediately and a write to fd 1 raises `EPIPE`/`SIGPIPE` immediately; neither can land on or read from either wire pipe, so the authentication hole is closed regardless of how the question below is eventually settled. This is a minimal denial, not an answer: it says "the confined command cannot forge the control channel," not "here is where its own output goes." The question this draft exists to hold -- what the supervised command's stdin/stdout/stderr *should* be wired to, for an embedder to actually read, including the TIOCSTI/claims-wiring consequences the two updates above already recorded -- is unchanged and still open.

**Correction, same review pass**: the first cut of this fix used `os.open(os.devnull, os.O_RDWR)` instead of a sealed pipe -- `/dev/null` being the obvious, idiomatic "nowhere" for a discarded stream. Measured against real bwrap in a privileged `ubuntu:24.04` container: that raised `PermissionError: [Errno 13] Permission denied: '/dev/null'` from *inside* the jail, even under `WHOLE_HOST_READ_ONLY`'s own whole-host-root bind -- breaking the walking skeleton itself (every real jailed command, not only an adversarial one), caught by this task's own instruction to re-verify against real bwrap rather than trust a macOS-only green run. A device node's openability inside a confined mount namespace is not guaranteed by any filesystem policy this module can assume (rule 2's jail-type-agnostic reasoning extends to this); a plain `os.pipe()` is a kernel object with no path to resolve and no device permission to check, so it has no such dependency and is the mechanism that actually shipped.

**A further, narrower question this adversarial review raised and measured, not fully this draft's own scope**: does sealing the supervised command's own fd 0/1 actually stop it from reaching the events pipe at all, given `WHOLE_HOST_READ_ONLY` also makes the jail's `/proc` reachable, and `/proc/<supervisor's pid>/fd/1` names the same pipe regardless of what the confined process's *own* fd table says? Measured, real bwrap, same container: with the fix above, the supervised command cannot open `/proc/<supervisor>/fd/1` nor read anything but `PATH` from `/proc/<supervisor>/environ` (the kernel's own ptrace-permission model denies a child introspecting its own parent this way under this host's default Yama settings, and `_start`'s own env for the supervisor was separately narrowed to just `PATH`, below). That measurement is specific to this one relationship (supervisor and its direct child, this host's ptrace_scope) and says nothing about `WHOLE_HOST_READ_ONLY`'s own, much broader habit of making every other host process's `/proc` entry reachable from inside any jail regardless of this fix -- which is this policy's own open question, not this draft's, and is being filed separately rather than claimed settled here.

**A related fix, same review pass, to `infra/supervisor/link.py`'s `_start`**: decision-0002's own request-channel finding (6) measured that handing the supervisor process "this process's own environment" (an earlier correction, replacing a single mapping shared with the supervised command) was *also* not safe on its own -- the same `/proc` reachability above means an embedder's real secrets, sitting in that environment for reasons having nothing to do with brig, were one `/proc/<supervisor>/environ` read away from the very command they were never meant to reach. `_start` now gives the supervisor process a fixed, minimal, non-secret environment (`PATH` alone, the one thing `posix_spawnp("bwrap", ...)` actually needs) instead.

## Fix-confirmation update: the sealed pipe silently rewrites the exit code of any command that writes to stdout

Measured while re-verifying the adversarial-review fixes, through brig's public API
(`create_bwrap_jail`/`run_jail`) against real bwrap in a `--privileged ubuntu:24.04`
container, and reproduced at the `link.py` layer on macOS:

| supervised command | `run_jail` returns | should be |
| --- | --- | --- |
| `/bin/true` | 0 | 0 |
| `/bin/sh -c "echo hello; exit 0"` | 0 | 0 |
| `/bin/sh -c "echo hello; exit 7"` | 7 | 7 |
| `/bin/echo hello` | **1** | **0** |
| `/bin/sh -c "echo oops 1>&2; exit 0"` | 0 | 0 |

The walking skeleton is intact -- this is *not* the `/dev/null` class of breakage, which
failed every jailed command. But `/bin/echo hello` is an ordinary, non-adversarial
command that succeeds outside a jail and reports failure inside one. The cause is the
sealed pipe itself: fd 1's read end is closed in `_start_child`'s own `finally`, so the
command's first write gets `EPIPE`/`SIGPIPE` with no reader anywhere, and whatever the
command does about that becomes its exit code. coreutils `echo` catches the write error
and exits 1; a command leaving `SIGPIPE` at its default disposition would be killed
outright and report `-13`; `sh`'s builtin `echo` fails but lets the script's own
`exit 0` stand. Which of the three happens is the command's business, not brig's --
brig's part is that the exit code it hands the embedder is no longer the exit code the
same command would have had outside the jail.

Two reasons this is worth recording rather than leaving implicit in "a write to fd 1
raises `EPIPE`/`SIGPIPE` immediately", which is all this draft said before:

1. **It is silent.** Before the fix, a command writing to stdout corrupted the event
   stream loudly -- `WireError` -> `SupervisorDoneUnknown` -> `JailExitUnknown`, a brig
   type the embedder catches. After the fix, `run_jail` returns a plausible-looking
   wrong integer and nothing anywhere says a write failed. The honest-command case
   traded a loud failure for a quiet one.
2. **It reaches grading.** `tests/e2e/test_tiocsti_battery.py` encodes an errno in its
   probe's exit code (`_ERRNO_EXIT_OFFSET`). Any battery probe that writes to stdout
   before exiting now has that encoding overwritten by an EPIPE-derived code, which
   `_evidence_from_measured_exit_codes` cannot tell from a real measurement. The
   existing `ENOTTY` skip covers today's probe's fd 0; this is the same hazard on fd 1,
   not yet hit only because no current probe writes to stdout.

Not fixed here, and deliberately so: the fix is to give the supervised command a real
stdout, which is exactly the design question this draft exists to hold. Noted so that
whoever settles it knows the sealed pipe is a *stopgap with its own cost*, not a
neutral placeholder -- and so nobody reads the current green suite as evidence that
jailed commands' exit codes are faithful. Note also that fd 2 is untouched by
`_start_child`: the supervised command's stderr still inherits the supervisor's, so
stderr-writing commands are unaffected (measured above), which is itself an
inconsistency the eventual design should resolve rather than preserve by accident.
<!-- SECTION:DESCRIPTION:END -->
