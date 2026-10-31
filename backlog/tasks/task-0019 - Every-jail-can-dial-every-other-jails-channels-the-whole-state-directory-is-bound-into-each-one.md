---
id: TASK-0019
title: >-
  Every jail can dial every other jail's channels: the whole state directory is
  bound into each one
status: To Do
assignee:
  - '@claude'
created_date: '2026-10-31T11:00:00Z'
labels:
  - size-3
dependencies: []
references:
  - >-
    backlog/tasks/task-0001.28 -
    Grade-channel_exclusivity-declared-channels-plus-enumerated-shared-media-from-the-readiness-batterys-evidence.md
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
- [ ] #3 channel_exclusivity's enumeration counts a dialable shared medium, read-only or not, so a regression grades the claim down instead of passing silently
<!-- AC:END -->
