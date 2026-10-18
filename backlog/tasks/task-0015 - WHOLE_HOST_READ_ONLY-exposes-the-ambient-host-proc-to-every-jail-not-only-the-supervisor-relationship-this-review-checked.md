---
id: TASK-0015
title: >-
  WHOLE_HOST_READ_ONLY exposes the ambient host /proc to every jail, not only
  the supervisor relationship this review checked
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 07:18'
updated_date: '2026-10-18 22:05'
labels:
  - brig
  - size-3
  - finish-moved
dependencies: []
references:
  - >-
    backlog/decisions/decision-0004 -
    WHOLE_HOST_READ_ONLY-gives-every-jail-a-namespace-scoped-proc-and-dev-and-masks-sys-instead-of-the-ambient-hosts-own.md
modified_files:
  - src/brig/domain/jail_types/bwrap.py
  - tests/unit/test_bwrap_compile.py
  - tests/e2e/test_fs_policy_battery.py
  - tests/e2e/test_tiocsti_battery.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Description

`WHOLE_HOST_READ_ONLY` (`domain/policy/paths.py`) -- the default `FsPolicy` every
bwrap jail gets until an embedder names its own, documented as "the thinnest policy
that lets the supervisor's own file be reachable inside the jail at all" -- binds
the whole host root (`--ro-bind / /`) with no exclusions. That bind is recursive:
it carries along whatever is already mounted at `/proc` on the host, so a real
bwrap jail under this default policy gets the *ambient host's* `/proc`, not a fresh
one scoped to the jail's own PID namespace (bwrap does not auto-mount `/proc`
unless told to with `--proc`).

Measured consequence, found while verifying TASK-0001.15/.16/.17's adversarial-review
fixes against real bwrap (a privileged `ubuntu:24.04` container): a jailed command
can `os.listdir("/proc")` and see every process on the host, by its real host-side
pid, not only its own jail's. For the one relationship this review actually tested
(the supervisor and its own direct child), the kernel's own ptrace-permission model
denied the child reading the supervisor's `/proc/<pid>/fd/1` or `/proc/<pid>/environ`
-- this host's default Yama `ptrace_scope` only allows a process to introspect its
*descendants*, and the child is not an ancestor of its own parent. That measurement
does not generalize: nothing about `WHOLE_HOST_READ_ONLY` prevents a jailed command
from listing, and attempting to introspect, *every other* process on the host --
only the specific supervisor/child relationship was checked, under this one host's
ptrace settings, which decision-0001's own "knows nothing of the programs that embed
it" framing gives no reason to assume every deployment shares.

## Open questions

- [ ] Should `WHOLE_HOST_READ_ONLY` (or its eventual real per-embedder-policy
  successor) exclude `/proc` -- and `/sys`, likely the same question -- by default,
  the way the filesystem battery's own "mirror policy" already excludes virtual
  filesystems it has no use for (TASK-0001.16's own precedent, `tests/e2e/test_fs_policy_battery.py`)?
- [ ] If a jail's supervisor and real command ever need their own, intentionally
  namespaced `/proc` (so the jail's own view of `/proc` reflects only its own PID
  namespace, per `--proc`), does that fully close this, or only reduce its blast
  radius to processes that genuinely share the jail's own namespace?
- [ ] Is relying on the host's own Yama `ptrace_scope` an acceptable part of this
  library's threat model at all, given brig's own stated goal of grading what is
  actually enforced rather than what a particular host's default configuration
  happens to allow -- or does every claim resting on it need its own battery, the
  way TIOCSTI's closure already has one for `--new-session`?

## Context

Not a finding against TASK-0001.15/.16/.17's own six reported issues -- it is a
broader, pre-existing property of `WHOLE_HOST_READ_ONLY` itself (present before the
supervisor existed, for any jailed command able to read any host path), surfaced
while re-verifying one of those six fixes (the control-channel authentication hole,
DRAFT-0010) against real bwrap. See DRAFT-0010's own latest update for the specific,
narrower measurement (supervisor vs. its own direct child) that fix's own review
pass actually checked and closed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 domain/jail_types/bwrap.py's compile_supervisor_launch adds --proc /proc --dev /dev --tmpfs /sys unconditionally, after state_dir's own bind and before the namespace flags -- a new named constant, not folded into _NAMESPACE_FLAGS
- [x] #2 A real-bwrap test proves a jail's own /proc listing contains only its own namespace's processes, not the host's (measured today: without the fix, 1/8/9 real host pids; with it, exactly 1 -- itself)
- [x] #3 A real-bwrap test proves /sys is empty inside the jail
- [x] #4 The existing walking-skeleton journey and every other real-bwrap battery still pass unmodified -- the new flags must not break the basic create/run/destroy path
- [x] #5 tests/unit/test_bwrap_compile.py's byte-exact assertion on compile_supervisor_launch's output is updated for the new flags, proving nothing else in the compiled argv changed
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Measured already (decision-0004), reuse directly -- don't re-derive

- Without --proc: a real jail's /proc listing contains real host pids (1, 8, 9 measured).
- With --proc /proc added: listing contains exactly 1 (the jail's own process, correctly
  namespace-scoped) -- a structural fix, not a mitigation riding on ptrace_scope.
- --dev /dev confirmed not to break the walking skeleton's basic command (true, exit 0).
- --tmpfs /sys (added after the ro-bind, so it shadows the recursive host mount) lists
  nothing -- sysfs has no per-namespace scoping to offer instead, so masked-empty is the
  only safe default.

### Order of work

1. Add a new named constant in domain/jail_types/bwrap.py (e.g. `_VIRTUAL_FS_FLAGS =
   ("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/sys")`) -- document why it's
   separate from `_NAMESPACE_FLAGS` (virtual-filesystem hygiene, not namespace/behavior
   flags) and why it's unconditional, never part of the caller's own FsPolicy, same
   framing as `state_dir`'s own bind.
2. Insert it into `compile_supervisor_launch`'s returned argv: after the state_dir bind,
   before `_NAMESPACE_FLAGS`.
3. Update `tests/unit/test_bwrap_compile.py`'s byte-exact assertion for the new flags.
4. New real-bwrap tests in tests/e2e/test_fs_policy_battery.py: /proc listing contains
   only the jail's own namespace (reuse the exact measurement shape from decision-0004);
   /sys is empty.
5. Re-run the full existing e2e/integration suite against real bwrap to confirm nothing
   regresses -- the walking skeleton, fs-policy battery, supervisor batteries all still
   need to pass with these new flags unconditionally present.

### Proof

- just gates, just typecheck, just done green on macOS.
- Real Linux + bwrap (brig-probe-amd64:latest): new tests pass, full suite still green,
  not just the new/changed tests in isolation.

### Risks

- Argv ordering: --proc/--dev/--tmpfs must come after state_dir's own bind (so they
  aren't shadowed by it) and the policy's own binds, consistent with "later wins" bwrap
  semantics already established in this file's own docstrings -- verify against real
  bwrap, don't just reason about ordering.
- Confirm nothing in brig's own code (supervisor, driver, any test) reads the host's
  real /proc, /sys, or /dev from inside a jail -- decision-0004 states this is already
  confirmed true (the supervisor's own reap loop is a pure syscall), re-verify rather
  than re-assume now that the actual change is landing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added `tests/e2e/test_tiocsti_battery.py` to modified files beyond the plan's own list: its `_bwrap_argv_prefix` is a hand-maintained mirror of `compile_supervisor_launch`'s compiled argv (TASK-0009's own precedent), cross-checked byte-exact against the real output in `tests/unit/test_bwrap_compile.py`. Leaving it stale would have made that cross-check test fail, and it is also the live argv the TIOCSTI differential probes spawn bwrap with directly, not merely a stale docstring risk. Updated both its returned tuple and its docstring (which enumerates what it mirrors) for the new `_VIRTUAL_FS_FLAGS`.

Check `uv run just done` exited 0

(205 earlier lines omitted)
```text
[2m21:39:45.171[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react-default-project[39m[0m
[2m21:39:45.171[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m21:39:45.172[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m21:39:45.172[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m21:39:45.176[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m21:39:45.433[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 269ms
[2m21:39:45.435[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /Users/brukhabtu/Downloads/brig-seed/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m21:39:45.436[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 489ms[39m[0m

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
INFO    -  Documentation built in 1.50 seconds

== architecture validate: PASS ==
[2m21:39:46.393[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m21:39:46.397[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /Users/brukhabtu/Downloads/brig-seed/docs/architecture[0m
[2m21:39:46.405[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m21:39:46.405[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m21:39:46.518[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 26 source files[0m
[2m21:39:46.597[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (26 files)[22m[0m
[2m21:39:46.597[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 204ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 19 elements, 19 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture

done: all steps passed
```

## Review (philosophy:reviewer, 2026-10-18)

Verdict: the work itself is sound and every acceptance criterion is genuinely met, but
the task cannot be closed by this review: the implementation is still uncommitted, and
this reviewer's own guardrail forbids it making commits. Two board/process blockers,
no technical blockers.

Evidence gathered independently (not from the worker's report):

- AC#1: `_VIRTUAL_FS_FLAGS = ("--proc","/proc","--dev","/dev","--tmpfs","/sys")` is its own
  constant, spliced literally into `compile_supervisor_launch`'s argv tuple after the
  state_dir `--ro-bind` triple and before `*_NAMESPACE_FLAGS`. No policy branch anywhere
  near it: genuinely unconditional.
- AC#2/#3 discrimination, the one real risk: measured in brig-probe-amd64:latest
  (privileged, linux/amd64, repo copied to /opt/brig). With the splice removed from the
  container's own copy, both probes return **exit 5** -- the specific "foreign pid found"
  and "/sys not empty" codes, not the "broken jail" code 4. The relaxation of
  decision-0004's literal "exactly 1" to "every numeric /proc entry is in {1, pid, ppid}"
  therefore still discriminates: the unfixed listing is the container's whole outer
  process tree and lands outside that set.
- AC#5 + argv mirror: `test_e2e_tiocsti_battery_bwrap_argv_prefix_matches_compile_supervisor_launch`
  is a real prefix equality against the compiled argv, and it fails on the reverted copy --
  so `test_tiocsti_battery.py`'s `_bwrap_argv_prefix` update was required and is byte-correct.
- AC#4: full suite in the container -- 122 passed, 3 skipped, mypy strict clean (62 files),
  pypeeker --strict clean. The 3 skips are all pre-existing environment skips (no
  /proc/self/fd race path, bwrap-missing mirror, no posix_spawn setsid); none introduced by
  --dev or --tmpfs. The TIOCSTI battery, the suite most exposed to --dev replacing /dev,
  runs and passes.
- macOS: record-check --tier full green (lint, unit, integration x2, e2e, docs, architecture
  validate + lint), just gates and just typecheck green. No file was reformatted or fixed by
  any check (git status unchanged across the runs).
- decision-0004's claim re-traced: `infra/supervisor/program.py` is stdlib-only, imports
  nothing under brig, and its reap loop is `os.waitpid(-1, 0)` (line 242) -- no /proc. The
  two /proc readers in `infra/processes.py` (`/proc/self/fd` enumeration, the `/proc/<pid>/stat`
  group scan) are host-side only and are not reachable from the in-jail supervisor.

Blockers (both for the worker, not technical):

1. The change is uncommitted (src/brig/domain/jail_types/bwrap.py,
   tests/unit/test_bwrap_compile.py, tests/e2e/test_fs_policy_battery.py,
   tests/e2e/test_tiocsti_battery.py). The reviewer cannot commit it.
2. `board-check close TASK-0015` refuses: all five acceptance criteria were added after
   the task was accepted in 81ffcf6, so it needs the `finish-moved` label plus a note
   saying what changed and why, committed with the work.

Low-severity finding, no draft filed (no realistic path to a failure, and it does not
weaken the claim): `_SYS_EMPTY_PROBE`'s control check is `os.path.exists(sys.argv[1])`
where argv[1] is `sys.executable` -- the interpreter already executing the probe. That is
near-tautological and cannot detect a broken jail the way `_READ_PROBE`'s control can. The
`os.listdir("/sys")` assertion itself is sound and was shown to discriminate.

Deviation accepted: AC#2's parenthetical "exactly 1" was a measurement note taken from bare
bwrap with no supervisor; through the public API the jail's own tree is supervisor-as-PID-1
plus the probe, so the subset form is the correct expression of the same criterion ("only
its own namespace's processes") and was proven to fail loudly without the fix.

### Two clarifications

- AC#4 read literally ("every other real-bwrap battery still pass **unmodified**") is not
  met: tests/e2e/test_tiocsti_battery.py is modified. Judged met anyway, deliberately --
  the only change in that file is its hand-maintained `_bwrap_argv_prefix` mirror of the
  compiled argv, which test_bwrap_compile.py's fidelity cross-check makes non-optional
  (proven: that test FAILS on the reverted copy). Every behavioral assertion in the battery
  is unchanged and passes. The AC's own gloss -- the new flags must not break the basic
  create/run/destroy path -- is met outright.
- All five criteria arrived at this review already ticked by the worker; this review's
  independent judgment agrees with every tick, so it changed none of them.
- 81ffcf6 ("Promote draft DRAFT-0012") is confirmed to be this task's own acceptance
  commit -- it renames this very file from DRAFT-0012 to TASK-0015 -- so board-check's
  finish-moved finding stands as stated.
- The commit set for the worker is five files, not the four dirty at review start: the
  four source/test files plus this task file, now dirty from these review notes.

finish-moved: promoted from a draft with no acceptance criteria, then given its real ACs in the same follow-up edit that set it In Progress -- drawn directly from decision-0004's own Consequences section, not a later scope change.

Independent review confirmed all 5 ACs genuinely met, with the one real risk (AC#2's relaxed {1, pid, ppid} assertion) specifically re-verified by reverting the splice in a container copy: unfixed /proc listing contains the container's whole outer process tree (exit 5, foreign pid found), confirming the test genuinely discriminates rather than passing regardless. Same revert-and-confirm for the /sys test. test_tiocsti_battery.py's argv-mirror fidelity test also confirmed to fail against the reverted copy. Full suite 122 passed/3 skipped on real Linux+bwrap, just gates/typecheck/done green on macOS. decision-0004's reap-loop claim verified directly: program.py's loop is a pure os.waitpid(-1, 0) syscall, no /proc reads, confirmed by reading the source.
<!-- SECTION:NOTES:END -->
