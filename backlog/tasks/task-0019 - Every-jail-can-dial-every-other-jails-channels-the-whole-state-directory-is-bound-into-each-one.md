---
id: TASK-0019
title: >-
  Every jail can dial every other jail's channels: the whole state directory is
  bound into each one
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T11:00:00Z'
updated_date: '2026-10-31T14:48:00Z'
labels:
  - size-3
  - finish-moved
dependencies: []
references:
  - >-
    backlog/tasks/task-0001.28 -
    Grade-channel_exclusivity-declared-channels-plus-enumerated-shared-media-from-the-readiness-batterys-evidence.md
modified_files:
  - src/brig/domain/jail_types/bwrap.py
  - src/brig/presentation/api.py
  - src/brig/presentation/errors.py
  - tests/unit/test_bwrap_compile.py
  - tests/e2e/test_tiocsti_battery.py
  - tests/e2e/test_cross_jail_channel_battery.py
type: bug
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Measured 2026-10-31 at a7e7f45 (Linux 6.18, bubblewrap 0.9.0, Python 3.15.0b4), through the public API only: jail B, whose own `FsPolicy` binds nothing under `BRIG_HOME`, connected to jail A's reserved channel and A answered.

Why: `compile_supervisor_launch` always appends `--ro-bind <state_dir> <state_dir>` (`domain/jail_types/bwrap.py`; reachability checked in `presentation/api.py`), and the state directory holds every jail's channel directory (`channels/<id>/`) and supervisor script. A read-only mount does not stop `connect()` on a Unix socket inside it, and `--unshare-all`'s network namespace does not cover path-named sockets. So every jail can list and dial every other jail's channels, whichever embedder or user session created them.

`CHANNEL_EXCLUSIVITY_CLAIM`'s enumeration (`writable_shared_paths`) misses it for the same reason: the state directory is shared read-only, and the claim only counts writable shared media, but a socket is dialled, not written.

Reproduction (any host with bwrap; `PY_TREE` is the interpreter's own tree, mounted so the supervisor can start):

```python
import os, sys
from pathlib import Path
import brig

PY_TREE = str(Path(sys.base_prefix).parent)
SYSTEM = [p for p in ("/usr", "/bin", "/lib", "/lib64", "/etc") if os.path.exists(p)]
POLICY = brig.FsPolicy(binds=tuple(brig.Bind(p, p) for p in [*SYSTEM, PY_TREE, sys.prefix]))
LISTEN = (
    "import socket, sys\n"
    "s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen(8)\n"
    "while True:\n"
    "    c, _ = s.accept()\n"
    "    try: c.sendall(b'A-answers')\n"
    "    except OSError: pass\n"
    "    c.close()\n"
)
DIAL = (
    "import socket, sys\n"
    "c = socket.socket(socket.AF_UNIX)\n"
    "try: c.connect(sys.argv[1]); print('DIALED', c.recv(20))\n"
    "except OSError as e: print('REFUSED', e)\n"
)
res = brig.reserve_channels((brig.Channel(name="a"),))
ep = res.reservations[0].endpoint
a = brig.create_bwrap_jail((sys.executable, "-I", "-c", LISTEN, ep), policy=POLICY, channels=res)
assert isinstance(brig.await_channel_ready(a, res.reservations[0], timeout_s=10), brig.ChannelReady)
b = brig.create_bwrap_jail((sys.executable, "-I", "-c", DIAL, ep), policy=POLICY)
brig.run_jail(b, timeout_s=10)  # B prints: DIALED b'A-answers'
brig.destroy_jail(b); brig.destroy_jail(a)
```

The listener survives brig's own readiness dial-and-leave first, so B's connect is not a race against a dead listener.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A bwrap jail sees no other jail's channel directory or supervisor script: of brig's state directory, at most its own channel directory and its own supervisor's file
- [ ] #2 An e2e battery plants the attempt above (a second jail dials the first's reserved endpoint) and fails if the connect succeeds, with a positive control that shows the same dial succeeds from the host
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Measure the mount sequence against real bwrap (done, 2026-10-31, bubblewrap 0.9.0): after the policy's binds, `--tmpfs <state_dir>`, `--ro-bind <own script> <own script>`, the channel directory's `--bind` when channels are declared, then `--remount-ro <state_dir>`. Under both `--ro-bind / /` and a narrow policy the jail lists only its own script and `channels/<own id>` in the state directory, cannot write the state directory or its script, writes its own channel directory, and sees no other jail's socket.
2. `domain/jail_types/bwrap.py`: `compile_supervisor_launch` takes `supervisor_script` (the file presentation wrote) and emits that sequence in place of `--ro-bind <state_dir> <state_dir>`. `writable_shared_paths` keeps its non-writable entry at `state_dir` (it now stands for the read-only mask, which shares nothing with the host) and adds the script's read-only bind, so its reconstruction still mirrors the compile. Docstrings that say the whole state directory is bound read-only are corrected.
3. `presentation/api.py`: `_supervisors_for` passes `supervisor_path[-1]`; docstrings of `_check_state_dir_reachable`, `_check_channel_directory_reachable` and `_supervisor_path`, and `presentation/errors.py`'s, follow. The reachability checks' logic stays: a tmpfs needs its mountpoint exactly as the bind did.
4. Tests: `tests/unit/test_bwrap_compile.py`'s byte-exact argv assertions; `tests/e2e/test_tiocsti_battery.py`'s `_bwrap_argv_prefix` takes the script path and its caller binds a real placeholder file in the state directory; a new e2e battery, `tests/e2e/test_cross_jail_channel_battery.py`: jail B dials jail A's reserved endpoint and must be refused, the same dial from the host succeeds (positive control), and B's view of the state directory holds only its own entries.

### Risks
- A policy shape that worked with the read-only bind and fails with the tmpfs: the mountpoint is created the same way, so `_check_state_dir_reachable`'s refusal still covers it; `test_fs_policy_battery.py` and the channel batteries run the shapes it names.
- `--remount-ro` must not be recursive, or the channel directory turns read-only: measured non-recursive above; the readiness and exclusivity batteries write sockets there.
- The TIOCSTI copy drifting: its unit-layer mirror test compares it with the compile.

### Proof
The new battery fails on a7e7f45 (B's dial connects) and passes after; `just done` passes, its e2e layer against real bwrap.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC #3 ("channel_exclusivity's enumeration counts a dialable shared medium, read-only or not") moved out, 2026-10-31, before any code: the claim is defined over writable shared paths, so counting read-only dialable media redefines old SPEC law 9's claim, and under WHOLE_HOST_READ_ONLY the default would then grade violated. That is a design decision for the owner, filed as a draft ("channel_exclusivity counts only writable shared paths, but a read-only bind of a host directory holding a socket is dialable"). This task removes the one such medium brig adds itself.

Check `uv run just done` exited 0

(268 earlier lines omitted)
```text
[31m │  × [0mClosed contribution model – community members can't report bugs
[31m │  × [0mCurrently unlicensed – unsuitable for production use
[31m │[0m
[31m │[0m  Our full analysis:
[31m │[0m
[31m │[0m  [4mhttps://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/[0m
[0m
INFO    -  mkdocs-likec4: No projects discovered, using default root project
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/brig/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig/docs
INFO    -  Documentation built in 4.70 seconds

== architecture validate: PASS ==
[2m14:48:20.782[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m14:48:20.799[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m14:48:20.844[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m14:48:20.845[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m14:48:21.208[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m14:48:21.402[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m14:48:21.403[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 622ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
