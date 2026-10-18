---
id: TASK-0014
title: >-
  infra.processes.spawn's SpawnError docstring is false on Linux: a missing
  argv[0] spawns successfully and dies 127
status: To Do
assignee: []
created_date: '2026-10-18 17:30'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
src/brig/infra/processes.py's spawn() docstring says 'Raises: SpawnError: argv[0] could not be found on PATH or exec'd'. Measured false on Linux (glibc): os.posix_spawnp with an unresolvable bare command name does NOT raise -- it returns a pid and the child exits 127 (/bin/sh reporting 'command not found'). Reproduced independently in brig-probe-amd64:latest (ubuntu:24.04 amd64, system CPython 3.12.3/glibc 2.39): os.posix_spawnp('definitely-not-real-xyz', [...]) -> NORAISE pid=9, waitpid status 32512 == 127<<8. On macOS the same call does raise FileNotFoundError -> SpawnError, which is why the claim went unnoticed. Consequence is sharper than a wrong docstring: on Linux a missing argv[0] yields a healthy-looking SpawnedProcess that the caller tracks, reaps, and sees exit 127 -- SpawnError never fires, and no layer above distinguishes 'the binary was missing' from 'the command ran and returned 127'. Found while reviewing TASK-0012, whose shape-1 e2e test had to fall back to a macOS-only skipif for exactly this reason (an engineered PATH-starving repro does not reproduce on Linux).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 spawn()'s docstring states Linux's actual posix_spawnp behaviour for an unresolvable argv[0] (no raise; child exits 127) rather than claiming SpawnError covers it
- [ ] #2 A decision is recorded on whether brig detects the shell-fallback/exit-127 shape explicitly, or accepts it, with the reasoning stated
<!-- AC:END -->
