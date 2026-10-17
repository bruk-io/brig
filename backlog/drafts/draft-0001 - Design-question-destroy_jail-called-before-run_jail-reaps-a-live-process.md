---
id: DRAFT-0001
title: 'Design question: destroy_jail called before run_jail reaps a live process'
status: Draft
assignee: []
created_date: '2026-10-17 21:17'
labels:
  - brig
dependencies: []
parent_task_id: TASK-0001
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
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

## Open questions

- [ ] Should `destroy_jail` reap the process itself (as part of teardown) before or
      instead of signalling, so destroy-without-run is well-defined and not a zombie
      exposure?
- [ ] Or should the public API's types make `destroy_jail` impossible to call before
      `run_jail` (e.g. `run_jail` consumes `Jail` and returns a new `Exited` value that
      `destroy_jail` additionally accepts, while `Jail` alone does not)?
- [ ] Or is "always call run_jail before destroy_jail" simply a documented contract on
      the public API, enforced by nothing, same as other call-order contracts already in
      the codebase?

Carried forward: TASK-0001.03's own walking skeleton does not need this answered -- its
one journey always runs the command before destroying the jail.
<!-- SECTION:DESCRIPTION:END -->
