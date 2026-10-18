---
id: TASK-0004
title: >-
  The supervised command's own stdin/stdout have nowhere to go: program.py's
  child inherits the wire pipes
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 04:34'
updated_date: '2026-10-18 12:06'
labels:
  - brig
  - size-3
  - finish-moved
dependencies: []
references:
  - >-
    backlog/decisions/decision-0002 -
    The-supervisor-request-channels-and-the-grading-skeleton-the-next-slices-shape.md
modified_files:
  - src/brig/infra/supervisor/wire.py
  - src/brig/infra/supervisor/program.py
  - src/brig/infra/supervisor/link.py
  - src/brig/infra/processes.py
  - tests/e2e/test_supervisor_program_gateway.py
  - tests/e2e/test_supervisor_link_gateway.py
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
command does about that becomes its exit code. Measured: coreutils `echo` catches the write
error and exits 1, while `sh`'s builtin `echo` fails but lets the script's own
`exit 0` stand. Inferred, not measured here: a command leaving `SIGPIPE` at its
default disposition would be killed outright and report `-13` -- no command in the
table above does that, so the table is not evidence of it. Which of the three happens is the command's business, not brig's --
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

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The wire protocol moves off fd 0/1/2 onto fixed fds (wire.py's REQUEST_FD/EVENTS_FD), freeing the supervised command's own stdin/stdout/stderr to inherit from the embedder exactly as they would with no supervisor in between
- [x] #2 program.py's _start_child explicitly closes the wire fds for the real command it starts, so it can never reach the control channel regardless of what its own fd 0/1/2 do
- [x] #3 infra.processes.spawn's fd redirection generalizes from stdin_fd/stdout_fd to an arbitrary target-fd mapping, correct regardless of this process's own fd-allocation state (measured: a source fd landing on its own target, or on another pair's target, is the common case at fd 3/4, not a rare one)
- [x] #4 Measured against real bwrap in a privileged Linux container: /bin/echo hello through run_jail returns 0 (not 1); test_tiocsti_battery.py's TIOCSTI-injection test stops skipping and passes; test_claims_wiring.py's tiocsti_closure claim grades ENFORCED again, not UNENFORCED
- [x] #5 just done green on macOS; lint/typecheck/gates and the full pytest suite green against real bwrap on Linux (Docker, privileged ubuntu:24.04)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Resolution

Of the two candidates this draft's own history named, picked the first: give `program.py`
its own fixed fds for the wire protocol (`wire.py`'s new `REQUEST_FD`/`EVENTS_FD`, 3/4),
leaving fd 0/1/2 free for the supervised command to inherit from whatever the jail type's
driver arranged -- exactly where they would have come from with no supervisor in between.
Rejected routing the real command's stdout through the wire protocol as a new event kind:
that is the log envelope decision-0002 already deferred to "after the supervisor lands",
not a fit for this draft's narrower question, and it would mean multiplexing/buffering a
binary stream through newline-delimited JSON for no reason once the simpler fix is available.

Gated on one measurement before writing any code (per review): does an inherited, explicitly
`set_inheritable` fd 4 survive `bwrap`'s own exec into a real jail under `--unshare-all`/
`--as-pid-1`? Measured yes, in a privileged `ubuntu:24.04` container -- fd passing is
independent of every namespace `bwrap` isolates.

### Changes

- `infra/supervisor/wire.py`: new public `REQUEST_FD = 3`/`EVENTS_FD = 4`, the fixed
  convention both ends agree on ahead of time (the same reasoning `_INHERITABLE_FDS`
  already uses for 0/1/2).
- `infra/supervisor/program.py`: reads the one exec request from `_REQUEST_FD` (duplicated
  by value, same convention as the message shapes), emits every event to `_EVENTS_FD`
  via a plain `os.write` (no second buffering layer). `_start_child` no longer seals fd 0/1
  with discard pipes -- it gives the real command no file action for 0/1/2 at all (plain
  inherit) and explicitly `POSIX_SPAWN_CLOSE`s `_REQUEST_FD`/`_EVENTS_FD` instead, which is
  the actual authentication-hole guard now (closing the *new* channel's numbers, since
  those -- not 0/1/2 -- are what the supervisor process itself still has open and
  inheritable at that point).
- `infra/processes.py`: generalized `spawn`'s `stdin_fd`/`stdout_fd` (fixed to the new
  process's fd 0/1) into a single `fds: Mapping[int, int]` (target -> this process's own
  source), since `link.py` now needs 3/4, not 0/1. Added `_resolve_fd_sources`: every
  source that collides with any target -- including its own, since `dup2(fd, fd)` is a
  documented no-op that does not clear a pipe fd's close-on-exec flag -- is relocated via
  `os.dup` first. Measured this is the *common* case at fd 3/4, not a rare one: an
  unencumbered process's first `os.pipe()` call returns the next fd past its standard
  streams, which is exactly 3.
- `infra/supervisor/link.py`: `_start` now passes `fds={wire.REQUEST_FD: ..., wire.EVENTS_FD:
  ...}` and `inheritable_fds=(0, 1, 2)` (was `()`) for the supervisor's own spawn -- the
  second change is what actually restores the supervised command's real stdio: it is what
  lets the supervisor itself keep the embedder's real fd 0/1/2 instead of having them closed
  before the supervised command ever starts.
- Test blast radius: `tests/e2e/test_supervisor_program_gateway.py` and
  `test_supervisor_link_gateway.py` moved off `Popen(stdin=PIPE, stdout=PIPE)` onto explicit
  `os.posix_spawn` with the same fd-collision-safe placement, since the wire protocol no
  longer lives on a subprocess's ordinary stdin/stdout; `_FAKE_SUPERVISOR_SCRIPT` now writes
  to `wire.EVENTS_FD` directly. The forged-`done` test's docstring was rewritten honestly:
  the mechanism changed (the forging write now lands on the test's own real stdout, never
  reaching the events channel at all, rather than raising `EPIPE` against a sealed pipe).

### A real bug this surfaced, fixed as part of this draft (not a separate filing)

Measured, not assumed: `os.posix_spawn`'s `POSIX_SPAWN_CLOSE` file action on a fd that is not
open at all fails the *whole* spawn with `EBADF` (confirmed directly:
`os.posix_spawnp('true', ['true'], os.environ, file_actions=[(os.POSIX_SPAWN_CLOSE, 37)])`
raises `OSError: [Errno 9] Bad file descriptor`) -- not silently ignored, contrary to a plain
reading of the POSIX spec text. `_read_exec_request` originally closed its own `_REQUEST_FD`
immediately after reading (`with os.fdopen(...)`), before `_start_child`'s own `file_actions`
tried to close that same number for the real command -- failing every supervised command's
spawn outright (`OSError: Bad file descriptor` for `sh`, the real interpreter, everything).
Fixed: `_read_exec_request` opens `_REQUEST_FD` with `closefd=False` and leaves the fd itself
open; `_main` closes this process's own copy only after `_start_child` has returned.

### Proof

- `just done` green in full on macOS (lint, typecheck, gates, pypeeker rule tests, unit,
  integration x2, e2e -- 20 passed/11 skipped with measured bwrap-unavailable reasons --
  docs, arch-validate, arch-lint).
- Real Linux + real bwrap, `docker run --platform linux/amd64 --privileged ubuntu:24.04`
  (the `brig-probe-amd64` image already built for this repo in this session), repo copied
  in, `uv sync`: `pytest tests/ pypeeker_rules/tests -rs` -> 79 passed, 2 skipped (both with
  measured reasons already on record, unrelated to this draft). `just lint`/`typecheck`/
  `gates` all clean there too (ruff installed via `uv tool install ruff`, the same gap
  TASK-0001.20 already tracks).
- The draft's own three-part oracle, measured directly against real bwrap in that container:
  1. `create_bwrap_jail(('/bin/echo', 'hello'))` through `run_jail` returns `0` (was `1`).
  2. `tests/e2e/test_tiocsti_battery.py::test_tiocsti_injection_fails_in_a_real_bwrap_jail`
     passes outright -- no longer the measured `ENOTTY` skip.
  3. `test_claims_wiring.py`'s `tiocsti_closure` claim, measured directly:
     `Evidence(control_observed=True, violation_blocked=True)` -> `Grade.ENFORCED` (was
     `UNENFORCED` on this same host before this draft's fix).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
### Review follow-up (same session)

A review pass flagged that the forged-\`done\` regression test no longer exercises the
invariant it names: once fd 1 became the embedder's real stdout again, writing a forged
event there passes whether or not \`_start_child\`'s \`POSIX_SPAWN_CLOSE\` actions for
\`wire.REQUEST_FD\`/\`wire.EVENTS_FD\` are even present. Added
\`test_a_supervised_commands_direct_write_to_the_events_fd_cannot_reach_it\` to
\`test_supervisor_link_gateway.py\`, writing the forged event to \`wire.EVENTS_FD\` by
number instead of through fd 1. Checked for discrimination, not only that it passes
(the same discipline \`test_supervisor_reaps_orphans.py\` was already held to): with the
two \`POSIX_SPAWN_CLOSE\` actions temporarily removed from \`_start_child\`, this new test
fails (\`assert 0 is None\` -- the forged exit code 0 is trusted early); restored, it
passes. \`_start_child\`'s own docstring now states the load-bearing ordering this
depends on explicitly (\`_REQUEST_FD\` must still be open when this function runs, which
holds only because \`_main\` closes it after, not before, calling this function) --
previously only \`_read_exec_request\`'s docstring said so, and that paragraph had gone
stale (it claimed \`_read_exec_request\` already closed its own copy, which stopped
being true once \`closefd=False\` was introduced earlier in this same task).

Re-verified after: \`just done\` green on macOS (21 e2e passed, up from 20); real Linux +
real bwrap (same Docker setup) -- 80 passed, 2 skipped, up from 79.

Check `uv run just done` exited 0

(184 earlier lines omitted)
```text
[2m08:14:21.130[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m08:14:21.130[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m08:14:21.131[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m08:14:21.131[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m08:14:21.135[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m08:14:21.393[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 269ms
[2m08:14:21.395[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m08:14:21.396[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 485ms[39m[0m

   ┌───────────────────────────────────────────────────────────────┐
   │                                                               │
   │                                                               │
   │   [2mWebcomponents generated to:[22m                                 │
   │    site/assets/mkdocs_likec4/likec4_views.js                  │
   │                                                               │
   │   [2mSetup and usage instructions:[22m                               │
   │    [34mhttps://likec4.dev/tooling/code-generation/webcomponent/[39m   │
   │                                                               │
   │                                                               │
   └───────────────────────────────────────────────────────────────┘

uv run mkdocs build --strict

[31m │  ⚠  Warning from the Material for MkDocs team[0m
[31m │[0m
[31m │[0m  MkDocs 2.0, the underlying framework of Material for MkDocs,
[31m │[0m  will introduce backward-incompatible changes, including:
[31m │[0m
[31m │  × [0mAll plugins will stop working – the plugin system has been removed
[31m │  × [0mAll theme overrides will break – the theming system has been rewritten
[31m │  × [0mNo migration path exists – existing projects cannot be upgraded
[31m │  × [0mClosed contribution model – community members can't report bugs
[31m │  × [0mCurrently unlicensed – unsuitable for production use
[31m │[0m
[31m │[0m  Our full analysis:
[31m │[0m
[31m │[0m  [4mhttps://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/[0m
[0m
INFO    -  mkdocs-likec4: No projects discovered, using default root project
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /Users/brukhabtu/Downloads/brig-seed/site
INFO    -  mkdocs-likec4: Generating web component for default project from /Users/brukhabtu/Downloads/brig-seed/docs
INFO    -  Documentation built in 1.87 seconds

== architecture validate: PASS ==
[2m08:14:22.364[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m08:14:22.367[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m08:14:22.375[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m08:14:22.376[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m08:14:22.487[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m08:14:22.571[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m08:14:22.571[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 208ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

### Review (not closed): AC#3 has a measured counterexample

Verdict: **not closed**, left In Progress. AC#1, #2, #4, #5 verified met; AC#3 is not met
as worded ("correct regardless of this process's own fd-allocation state").

**Blocking finding -- `_resolve_fd_sources` can relocate a source *onto a target*, and
`_fd_actions` then closes it.** `os.dup` returns the lowest free fd number, and a target
number (3 or 4) is a candidate whenever it is free -- contrary to that function's own
docstring, which justifies the relocation by claiming targets "are not fds this process
has open at all" and therefore cannot be returned. Measured on macOS, through the real
code, no mocking:

```
a, b = os.pipe()   # 3, 4
c, d = os.pipe()   # 5, 6
os.close(b)        # fd 4 free, lowest; 3/5/6 open
_resolve_fd_sources({3: a, 4: d})
  -> resolved {3: 4, 4: 6}, relocated (4,)
_fd_actions(resolved)
  -> [DUP2 4->3, DUP2 6->4, CLOSE 4, CLOSE 6]
```

The `CLOSE 4` closes the fd the preceding `DUP2 6->4` just put the events channel on.
Confirmed end to end through `processes.spawn(..., fds={3: a, 4: d})` in that same fd
layout: the spawned child reports `fd4 FAILED: [Errno 9] Bad file descriptor` on
`os.write(4, ...)`. In the supervisor's real use that is the events channel absent from
`program.py`, silently, for an embedder whose fd table happens to have a hole at 3 or 4
-- the exact "regardless of allocation state" property AC#3 claims. The fix is to exclude
the target set when relocating (dup until the result is outside `targets`, or dup with a
minimum via `fcntl.F_DUPFD` past `max(targets)`), and to not `CLOSE` a source number that
is itself a target.

**Supporting finding (why it shipped): the collision path has zero regression coverage.**
With the whole `if source in targets:` relocation branch deleted in a container copy, the
suite stays green (`pytest tests/` -> 58 passed, 2 skipped on privileged
`ubuntu:24.04`/amd64). Under `uv run`/pytest the two pipes land at fds 12-15, so no
collision ever occurs in the suite -- a test must force the allocation state, not merely
drive `link.py`. Independently measured that the branch *is* load-bearing: with
`_resolve_fd_sources` monkeypatched to the naive identity on macOS (where the pipes do
land at 3-6), `LiveSupervisors.start(("/bin/echo", "hello"))` fails outright --
`program.py` raises `OSError: [Errno 9] Bad file descriptor` at `_read_exec_request`,
surfacing as `SupervisorSpawnError`. Filed as DRAFT for the coverage, alongside the fix.

### What was verified and does hold

- **AC#1**: wire protocol genuinely on `wire.REQUEST_FD`/`EVENTS_FD` (3/4); `link._start`
  passes `fds={3: ..., 4: ...}` and `inheritable_fds=(0, 1, 2)`; `program.py` reads/writes
  only those numbers and gives the real command no file action for 0/1/2. Measured: a real
  supervised `/bin/echo hello` printed `hello` on this reviewer's own terminal and
  returned 0.
- **AC#2**: `_start_child`'s two `POSIX_SPAWN_CLOSE` actions are present and
  **discriminating**, not asserted: with both removed in a container copy,
  `test_a_supervised_commands_direct_write_to_the_events_fd_cannot_reach_it` is the one
  test that fails (1 failed, 5 passed in that file). The review follow-up genuinely fixed
  the regression test rather than only noting the gap -- the confused-deputy hole
  TASK-0001.15's adversarial review found is re-proved closed under the fd-3/4 design.
- **AC#5**: `record-check --tier full` on macOS -- all steps passed, no files reformatted
  or fixed by the run (`git status` unchanged after it). Fresh privileged
  `--platform linux/amd64 ubuntu:24.04` container (`brig-probe-amd64:latest`), repo copied
  in, `uv sync`, `pytest tests/ pypeeker_rules/tests -rs` -> **80 passed, 2 skipped**, both
  skips with measured reasons unrelated to this task.
- **AC#4** was verified independently by the dispatching reviewer and not re-derived here.

Two independent adversarial reviews, both with real measurements in a privileged ubuntu:24.04 Docker container against real bwrap, not taken on self-report:

AC#1 -- confirmed: wire protocol genuinely on fixed fds 3/4 (wire.py REQUEST_FD/EVENTS_FD); link._start passes fds={3:...,4:...} with inheritable_fds=(0,1,2); _start_child gives the real command no file action for 0/1/2. A real supervised /bin/echo hello printed to the reviewer's own terminal and returned 0.

AC#2 -- confirmed discriminating, not merely present: removing both POSIX_SPAWN_CLOSE actions in a container copy fails exactly the confused-deputy regression test (test_a_supervised_commands_direct_write_to_the_events_fd_cannot_reach_it). The confused-deputy hole TASK-0001.15's original review found stays closed under this fd-3/4 redesign.

AC#3 -- confirmed, after a real blocking bug was found and fixed as its own task (TASK-0005): the first review found infra.processes.spawn's fd-collision relocation could land a relocated source on one of fds's own target numbers (os.dup returns the lowest free fd, which is a target whenever there's a hole there), silently losing the events channel. Fixed in TASK-0005 (fcntl.F_DUPFD past max(targets)), independently re-verified by a second reviewer who reconstructed the pre-fix code and confirmed the exact measured failure, then confirmed the fix and its regression test both hold.

AC#4 -- confirmed directly, by me: create_bwrap_jail(('/bin/echo','hello')) through run_jail returns 0; test_tiocsti_battery.py's main claim test passes outright (not the ENOTTY skip); test_claims_wiring.py's _measure_tiocsti_closure() returns Evidence(control_observed=True, violation_blocked=True), the ENFORCED shape, on real Linux+bwrap.

AC#5 -- confirmed: record-check --tier full green on macOS (nothing reformatted); 80 passed/2 skipped in brig-probe-amd64:latest after TASK-0005's fix landed.

This redesign replaced an earlier stopgap (sealing the supervised command's fd 0/1 with discard pipes) that closed the same confused-deputy hole but silently corrupted exit codes for ordinary stdout-writing commands and degraded the tiocsti_closure claim from ENFORCED to UNENFORCED with no test failure -- both now restored. Committed together with TASK-0001.15/.16/.17/TASK-0005 in a485ee1, since this feature and TASK-0005's fix to it are textually inseparable (no earlier commit of this feature alone exists).
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: @claude
created: 2026-10-18 07:59

---

Acceptance criteria added after the draft's promotion to a task: the draft itself (DRAFT-0010) carried no AC, only an open design question plus a long measured history; promoting it to TASK-0004 is what first gave it AC, stated here as the resolution actually implemented and measured, not negotiated against a pre-existing set. finish-moved per board-check.

---
<!-- COMMENTS:END -->
