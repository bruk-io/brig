---
id: DRAFT-0001
title: 'Design question: destroy_jail called before run_jail reaps a live process'
status: Draft
assignee: []
created_date: '2026-10-17 21:17'
updated_date: '2026-10-17 21:54'
labels:
  - brig
dependencies: []
parent_task_id: TASK-0001
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Description

## Why

Found while implementing TASK-0001.03's presentation layer (ports.py, drivers/bwrap.py,
api.py, errors.py).

`presentation/api.py`'s `destroy_jail` calls `domain/teardown.py`'s verified kill ladder
directly on `jail.process`, with no requirement that `run_jail` (which reaps the
process) was ever called first. If an embedder calls `create_bwrap_jail` then
`destroy_jail` without an intervening `run_jail`, the process is still running (or, if it
already exited, is an unreaped zombie): `teardown`'s first `Verify` finds it alive (a
zombie's pid is not freed until reaped -- `infra/processes.py`'s own `is_alive`
docstring says so), so the ladder sends TERM then KILL to a jail that may already have
exited, and still raises `JailTeardownFailed` in the zombie case because a zombie keeps
answering `is_alive` as true until something calls `waitpid` on it -- which nothing in
this path ever does.

This is outside the walking skeleton's own AC (its journey is create -> run -> destroy,
in order), so it wasn't blocking TASK-0001.03, but it's a real gap in the public API's
contract once more than one embedder call-site exists.

**Resolved in TASK-0001.03**, after an adversarial review measured exactly this bug
(spawning a real process and driving the real teardown ladder against it: TERM -> ALIVE
-> KILL -> ALIVE -> `JailTeardownFailed`, with the zombie confirmed left behind
afterwards). The fix took the first open question's answer below: `teardown`'s `Verify`
now reaps non-blockingly (`infra/processes.py`'s `reap_nowait`, `os.waitpid(pid,
WNOHANG)`) before checking the group with `group_alive` (`os.killpg(pgid, 0)`, not a
single-pid probe), on every verify in the ladder, and the last rung adds a blocking
`Reap` after `SignalKind.KILL` (safe because that signal cannot be ignored) so the
final verify is deterministic. Re-measured the same way the review found it: a real
`sleep` process, never run through `run_jail`, destroyed directly -- now returns `GONE`
with no zombie left (`ps` confirms), and a second `destroy` on the same process is a
no-op `GONE`, not an exception. destroy-without-run and destroy-called-twice are both
well-defined now.

What is *not* resolved: the narrower, POSIX-wide pid-reuse race once a pid genuinely
has been freed (by this reap, or by `run_jail`'s own reap on the ordinary path) and the
OS reassigns that exact pid to an unrelated process before the next probe. That residual
question has its own board task: DRAFT-0003, "Verified process identity across reap and
teardown (pidfd, or verify-before-reap)".

## Open questions

- [x] Should `destroy_jail` reap the process itself (as part of teardown) before or
      instead of signalling, so destroy-without-run is well-defined and not a zombie
      exposure? -- Yes: `teardown`'s `Verify` now does a non-blocking reap first, every
      time, and the ladder's last rung reaps once more (blocking, safely, since it
      follows an unignorable `KILL`) before its final verify.
- [ ] Or should the public API's types make `destroy_jail` impossible to call before
      `run_jail` (e.g. `run_jail` consumes `Jail` and returns a new `Exited` value that
      `destroy_jail` additionally accepts, while `Jail` alone does not)? -- Not needed:
      the reap-based fix makes destroy-without-run well-defined on its own, so this
      type-level option is no longer required to close the original gap. Carried
      forward only if a future reviewer wants the type system to rule the call order out
      entirely rather than make the out-of-order call safe.
- [ ] Or is "always call run_jail before destroy_jail" simply a documented contract on
      the public API, enforced by nothing, same as other call-order contracts already in
      the codebase? -- Superseded: the call order is now safe either way, so this is no
      longer the open question it was.

Carried forward: the pid-reuse race (see DRAFT-0003) is the one piece of this that
remains genuinely open.
<!-- SECTION:DESCRIPTION:END -->
