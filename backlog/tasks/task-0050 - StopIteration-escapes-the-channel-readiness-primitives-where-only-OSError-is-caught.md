---
id: TASK-0050
title: >-
  StopIteration escapes the channel-readiness primitives where only OSError is
  caught
status: In Progress
assignee: []
created_date: 2026-10-25 16:57
updated_date: '2026-11-04T13:51:00Z'
labels:
  - brig
  - channels
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-0001.27's review. Two places in src/brig/infra/sockets.py can raise StopIteration out of a function whose own contract says it never raises, because both catch OSError only and both read a /proc line with next(...):

1. channel_ready: pidfd_pid = next(int(line.split()[1]) for line in handle if line.startswith('Pid:')) over /proc/self/fdinfo/<pidfd>, inside a try whose only handler is 'except OSError: return ChannelRefused(PEER_LOOKUP_FAILED)'. The function's docstring states 'Every failure this function can reach is one of those three values, never a raise (decision-0005 item 5)' and names exactly one exception (the jail_namespace_fd readlink precondition). StopIteration is an unnamed second one.

2. jail_pid1_namespace: its scan loop catches OSError only, while _nspid uses next(...) over /proc/<pid>/status for the NSpid: line. _nspid's own docstring already specifies the intended behaviour -- 'a StopIteration (status carried no NSpid: line at all) ... mean[s] "this candidate is not the jail's PID 1", never "the scan is over"' -- and the code does not implement it: the StopIteration escapes the whole scan and reaches create_bwrap_jail untranslated.

Realistic path: _children's own docstring concedes a process can exit between the listdir and the read; a task read mid-exit can open status successfully and yield no NSpid: line, which raises StopIteration, not OSError. Same class as the ENOPROTOOPT/EINVAL misclassification fixed under TASK-0001.27: the docstring already specified the behaviour and the code did not implement it.

Does not breach TASK-0001.27 AC#4, whose enumeration is literally OSError.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 channel_ready returns ChannelRefused(PEER_LOOKUP_FAILED) rather than raising when /proc/self/fdinfo/<pidfd> carries no Pid: line, and a test pins it
- [ ] #2 jail_pid1_namespace skips a candidate whose status carries no NSpid: line and keeps scanning until its deadline, as _nspid's docstring already specifies, and a test pins it
- [ ] #3 No StopIteration escapes infra/sockets.py: _verify's fdinfo parse and jail_pid1_namespace's NSpid read each treat a missing line as their documented outcome; repro test: a fake proc_root child whose status has PPid but no NSpid makes jail_pid1_namespace raise StopIteration today
- [ ] #4 A test pins each site
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

Repro at 627b070b7545, test files: tests/e2e/test_sockets_nspid_missing.py; command: `uv run pytest tests/e2e/test_sockets_nspid_missing.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
_______ test_a_child_without_an_nspid_line_is_skipped_until_the_deadline _______

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-741/test_a_child_without_an_nspid_0')

    def test_a_child_without_an_nspid_line_is_skipped_until_the_deadline(tmp_path: Path) -> None:
        """bwrap is running and its one child's `status` carries `PPid:` but no `NSpid:`: no PID 1
        is found, so the scan answers `JailPid1NotFound` once its deadline passes."""
        proc_root = tmp_path / "proc"
        _plant(proc_root, _BWRAP, "Name:\tbwrap\nState:\tS (sleeping)\nPPid:\t1\nNSpid:\t3000\n")
        _plant(proc_root, _CANDIDATE, f"Name:\tgoing\nState:\tS (sleeping)\nPPid:\t{_BWRAP}\n")
    
>       outcome = sockets.jail_pid1_namespace(_BWRAP, time.monotonic() + 0.2, str(proc_root))
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/e2e/test_sockets_nspid_missing.py:36: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
src/brig/infra/sockets.py:143: in jail_pid1_namespace
    if _nspid(child, proc_root).split()[-1] != "1":
       ^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

pid = 3001
proc_root = '/tmp/pytest-of-root/pytest-741/test_a_child_without_an_nspid_0/proc'

    def _nspid(pid: int, proc_root: str = "/proc") -> str:
        """`pid`'s `NSpid` line: its pid in each PID namespace, outermost first. Its `OSError` and
        `StopIteration` (no `NSpid:` line) are left to the caller."""
        with open(f"{proc_root}/{pid}/status") as handle:
>           return next(line.split(":", 1)[1].strip() for line in handle if line.startswith("NSpid:"))
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E           StopIteration

src/brig/infra/sockets.py:110: StopIteration
=========================== short test summary info ============================
FAILED tests/e2e/test_sockets_nspid_missing.py::test_a_child_without_an_nspid_line_is_skipped_until_the_deadline
1 failed in 0.21s
```

Check `uv run just done` exited 0

(335 earlier lines omitted)
```text
[2m13:51:00.909[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m13:51:00.916[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m13:51:00.918[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m13:51:03.842[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 3.12s
[2m13:51:03.847[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m13:51:03.850[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.8s[39m[0m

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
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

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
INFO    -  Building documentation to directory: /home/user/brig-pins/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-pins/docs
INFO    -  Documentation built in 6.96 seconds

== architecture validate: PASS ==
[2m13:51:05.813[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m13:51:05.828[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m13:51:05.854[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m13:51:05.855[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m13:51:06.290[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m13:51:06.662[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m13:51:06.662[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 850ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Worker, 2026-11-04 (branch claude/small-bugs): repro 627b070 (tests/e2e/test_sockets_nspid_missing.py, recorded failing above on StopIteration out of _nspid), fix 867970c.

- AC#2/#3, jail_pid1_namespace: `_nspid` now returns `None` for a status with no `NSpid:` line (`next(..., None)`), and the scan skips that candidate and keeps going to its deadline. The comparison is now `nspid.split()[-1:] != ["1"]`, so an `NSpid:` line with nothing on it is skipped too instead of raising `IndexError` (a third escape of the same class, found while fixing).
- AC#1/#3, `_verify`: the fdinfo read is `next(..., None)`; `None` differs from the peer pid, so it is `PEER_LOOKUP_FAILED`. Docstrings of `channel_ready`, `_verify`, `_nspid` and `jail_pid1_namespace` say so.
- Seam: `channel_ready` gains a keyword `proc_root: str = "/proc"` (infra only, not brig's public API), used for `<proc_root>/<pid>/ns/pid` and `<proc_root>/self/fdinfo/<pidfd>`; the connect and the jail's namespace still go through the real `/proc/self/fd`. presentation passes nothing, so behaviour is unchanged.
- AC#4: tests/e2e/test_sockets_missing_proc_lines.py pins each site: a real listener with a planted fdinfo lacking `Pid:` is `ChannelRefused(PEER_LOOKUP_FAILED)`, its positive control (same tree with `Pid:` naming the listener) is `ChannelReady`; the scan finds PID 1 beside a no-NSpid child; an empty NSpid line is skipped. Planted fdinfo covers every fd number up to this process's highest open fd + 64, since the pidfd's number is the kernel's.
- Two e2e helpers (test_channel_readiness_kernel.py, test_channel_readiness_refusals.py) forwarded `**seams: int`, which mypy rejects now that one seam is a str; kernel's names `so_peerpidfd` instead, refusals' (which never passed one) takes none.
- `uv run just done`: all steps passed (recorded above). Criteria left for the reviewer.
<!-- SECTION:NOTES:END -->
