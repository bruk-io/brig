---
id: TASK-0052
title: >-
  A policy without the interpreter's ELF loader and libraries passes
  interpreter_refusal and fails in bwrap with execvp No such file
status: Done
assignee: []
created_date: '2026-11-03T03:46:00Z'
updated_date: '2026-11-04T14:23:00Z'
labels:
  - brig
  - fs-policy
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0029 at 55336cd. FsPolicy(readable=(.venv, ~/.local/share/uv/python)) passes interpreter_refusal; create_bwrap_jail then prints 'bwrap: execvp /home/user/brig/.venv/bin/python3: No such file or directory' and run_jail raises JailExitUnknown, the exact symptom TASK-0029 set out to replace: the dynamic loader (/lib64/ld-linux-*) and libc are not mounted. Also over-refuses: a policy naming the venv's python3 link itself as a readable root is refused naming .venv/bin/python, yet bwrap binding that link mounts its target and the interpreter execs (measured with bwrap directly). link_chain also normalises '..' lexically before following links, so a path like a/link/../b is resolved wrong.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 infra.files.link_chain resolves a/link/../b as the kernel does (the link first, then ..), not by normalising .. as text; a tmp-tree test pins it; repro test recorded failing
- [x] #2 A policy whose readable root is the venv's python3 link itself is not refused by interpreter_refusal
- [x] #3 The ELF loader and DT_NEEDED half is split out as a design draft of its own
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

Repro at 99f0ddc2dba1, test files: tests/e2e/test_files_link_chain_dotdot.py; command: `uv run pytest tests/e2e/test_files_link_chain_dotdot.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
_________ test_dotdot_after_a_link_is_taken_from_where_the_link_leads __________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-770/test_dotdot_after_a_link_is_ta0')

    def test_dotdot_after_a_link_is_taken_from_where_the_link_leads(tmp_path: Path) -> None:
        """`a/link -> ../x/y`, and both `a/b` and `x/b` exist: the chain ends at `x/b`, the file the
        kernel opens for `a/link/../b`."""
        (tmp_path / "a").mkdir()
        (tmp_path / "x" / "y").mkdir(parents=True)
        (tmp_path / "a" / "b").write_text("the text's answer")
        (tmp_path / "x" / "b").write_text("the kernel's answer")
        (tmp_path / "a" / "link").symlink_to("../x/y")
        path = f"{tmp_path}/a/link/../b"
    
        chain = files.link_chain(path)
    
>       assert os.stat(chain[-1]).st_ino == os.stat(path).st_ino
E       AssertionError: assert 814155 == 814156
E        +  where 814155 = os.stat_result(st_mode=33188, st_ino=814155, st_dev=65024, st_nlink=1, st_uid=0, st_gid=0, st_size=17, st_atime=1793801175, st_mtime=1793801175, st_ctime=1793801175).st_ino
E        +    where os.stat_result(st_mode=33188, st_ino=814155, st_dev=65024, st_nlink=1, st_uid=0, st_gid=0, st_size=17, st_atime=1793801175, st_mtime=1793801175, st_ctime=1793801175) = <built-in function stat>('/tmp/pytest-of-root/pytest-770/test_dotdot_after_a_link_is_ta0/a/b')
E        +      where <built-in function stat> = os.stat
E        +  and   814156 = os.stat_result(st_mode=33188, st_ino=814156, st_dev=65024, st_nlink=1, st_uid=0, st_gid=0, st_size=19, st_atime=1793801175, st_mtime=1793801175, st_ctime=1793801175).st_ino
E        +    where os.stat_result(st_mode=33188, st_ino=814156, st_dev=65024, st_nlink=1, st_uid=0, st_gid=0, st_size=19, st_atime=1793801175, st_mtime=1793801175, st_ctime=1793801175) = <built-in function stat>('/tmp/pytest-of-root/pytest-770/test_dotdot_after_a_link_is_ta0/a/link/../b')
E        +      where <built-in function stat> = os.stat

tests/e2e/test_files_link_chain_dotdot.py:29: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_files_link_chain_dotdot.py::test_dotdot_after_a_link_is_taken_from_where_the_link_leads
1 failed in 0.23s
```

Repro at 69e2edf88d58, test files: tests/unit/test_interpreter_link_root.py; command: `uv run pytest tests/unit/test_interpreter_link_root.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
FF..                                                                     [100%]
=================================== FAILURES ===================================
________ test_a_root_that_is_the_interpreter_link_itself_is_not_refused ________

    def test_a_root_that_is_the_interpreter_link_itself_is_not_refused() -> None:
        """The root is the first path of the chain: the jail sees the interpreter there."""
>       assert interpreter_refusal(FsPolicy(readable=("/usr", "/r/.venv/bin/python3")), _CHAIN) is None
E       AssertionError: assert InterpreterUnreachable(path='/r/.venv/bin/python') is None
E        +  where InterpreterUnreachable(path='/r/.venv/bin/python') = interpreter_refusal(FsPolicy(readable=('/usr', '/r/.venv/bin/python3'), writable=(), write_denies=(), masks=()), ('/r/.venv/bin/python3', '/r/.venv/bin/python', '/u/cpython-3.15/bin/python3.15', '/u/cpython-3.15.0b4/bin/python3.15'))
E        +    where FsPolicy(readable=('/usr', '/r/.venv/bin/python3'), writable=(), write_denies=(), masks=()) = FsPolicy(readable=('/usr', '/r/.venv/bin/python3'))

tests/unit/test_interpreter_link_root.py:20: AssertionError
_ test_a_root_that_is_a_later_path_on_the_way_is_not_refused_once_the_earlier_ones_are _

    def test_a_root_that_is_a_later_path_on_the_way_is_not_refused_once_the_earlier_ones_are() -> None:
        """Both venv links are inside `.venv`, and the path the second leads to, through the
        version's link, is a root of its own: bwrap binds the interpreter there."""
        policy = FsPolicy(readable=("/r/.venv", "/u/cpython-3.15/bin/python3.15"))
    
>       assert interpreter_refusal(policy, _CHAIN) is None
E       AssertionError: assert InterpreterUnreachable(path='/u/cpython-3.15.0b4/bin/python3.15') is None
E        +  where InterpreterUnreachable(path='/u/cpython-3.15.0b4/bin/python3.15') = interpreter_refusal(FsPolicy(readable=('/r/.venv', '/u/cpython-3.15/bin/python3.15'), writable=(), write_denies=(), masks=()), ('/r/.venv/bin/python3', '/r/.venv/bin/python', '/u/cpython-3.15/bin/python3.15', '/u/cpython-3.15.0b4/bin/python3.15'))

tests/unit/test_interpreter_link_root.py:28: AssertionError
=========================== short test summary info ============================
FAILED tests/unit/test_interpreter_link_root.py::test_a_root_that_is_the_interpreter_link_itself_is_not_refused
FAILED tests/unit/test_interpreter_link_root.py::test_a_root_that_is_a_later_path_on_the_way_is_not_refused_once_the_earlier_ones_are
2 failed, 2 passed in 0.20s
```

Check `uv run just done` exited 0

(351 earlier lines omitted)
```text
[2m14:10:17.631[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m14:10:17.647[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m14:10:17.700[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m14:10:19.585[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.00s
[2m14:10:19.587[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m14:10:19.590[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 2.8s[39m[0m

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
INFO    -  Documentation built in 5.33 seconds

== architecture validate: PASS ==
[2m14:10:21.006[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m14:10:21.024[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m14:10:21.075[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m14:10:21.075[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m14:10:21.491[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m14:10:21.832[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m14:10:21.832[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 827ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Worker, 2026-11-04 (branch claude/small-bugs): repros 99f0ddc (tests/e2e/test_files_link_chain_dotdot.py, AC#4) and 69e2edf (tests/unit/test_interpreter_link_root.py, AC#5), both recorded failing above; fix e39e676.

- AC#3/#4, `infra.files.link_chain`: walks the lookup component by component as the kernel does: `..` is taken from where the components before it lead, a link among them followed first. Each path in the chain is spelled with every component up to the next link resolved and the rest as written, so a `..` straight after a link is kept (`/t/a/link/../b`, then `/t/x/b`), never cancelled as text. For an ordinary path (no `..` after a link) the chain is exactly what it was. A relative path is now returned alone (before, its links were read against the working directory; both callers pass absolute paths or refuse a relative one first). tests/e2e/test_files_link_chain_kernel.py pins the venv chain shape, `..` inside a link's target, `..` before any link, a link to `/`, a link loop, a relative path, and a mixed case against `os.path.realpath` and `os.stat`.
- AC#5, `interpreter_refusal`: a chain path that is itself a readable or writable root ends the walk (after the inside-a-root and mask checks), since bwrap binds what a root leads to at the root's own path and the jail follows none of the links after it. Pinned by the unit repro (root = `.venv/bin/python3`; root = a later path on the way; a root on a later link does not excuse an earlier one; a mask still refuses) and by tests/e2e/test_interpreter_link_root_battery.py, which starts the supervisor under readable=(system, `.venv/bin/python3`, `.venv/pyvenv.cfg`, the base install's directory as `pyvenv.cfg`'s `home` names it) and sees exit 0. SPEC updated.
- AC#6 is met by DRAFT-0029 (the ELF half). AC#1 and AC#2 belong to that half and are not addressed here.
- Finding for the lead, not fixed: a policy of (system, uv's python directory, `.venv/bin/python3`) without `.venv/pyvenv.cfg` now passes `interpreter_refusal` (before this change it was refused, by the over-refusal AC#5 removes) and fails in the jail: the interpreter, a plain file at the link's path there, finds no `pyvenv.cfg`, cannot find its standard library (`ModuleNotFoundError: No module named 'base64'`), and `run_jail` raises `JailExitUnknown`. Measured with the real API on this host. It is the same class as DRAFT-0029 (the interpreter needs more than its link chain: its prefix and `pyvenv.cfg` too); worth folding into that draft's question.
- `uv run just done`: all steps passed (recorded above). Criteria left for the reviewer.

Lead, 2026-11-04 (finish moved, already labelled): the draft's own three criteria are removed. #1 (refuse a policy lacking the ELF interpreter or a needed library) is the ELF half, split out as DRAFT-0029. #2 (any policy bwrap can start the supervisor under is not refused) is replaced by its checkable case, the venv link root, as the draft review said (now #2 below). #3 duplicated the kernel-order link_chain criterion (now #1).

Check `uv run just done` exited 1

(498 earlier lines omitted)
```text
[2m14:20:08.984[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m14:20:11.880[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 3.16s
[2m14:20:11.890[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m14:20:11.892[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 4.3s[39m[0m

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
INFO    -  Documentation built in 7.15 seconds

== architecture validate: PASS ==
[2m14:20:13.881[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m14:20:13.911[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m14:20:13.982[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m14:20:13.983[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m14:20:14.774[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 40 source files[0m
[2m14:20:15.241[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (40 files)[22m[0m
[2m14:20:15.241[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.3s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 34 elements, 67 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

  e2e tests: FAILED tests/e2e/test_interrupt_battery.py::test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost
done: 1 step(s) failed: e2e tests
error: recipe `done` failed on line 71 with exit code 1
```

Reviewer, 2026-11-04: closed. Every criterion met. #1: link_chain walks component by component; a .. after a link is taken from the link's target (repro 99f0ddc failed, now passes; tests/e2e/test_files_link_chain_kernel.py checks against realpath/stat). #2: a chain path that is a root ends the walk after the inside and mask checks (repro 69e2edf; the e2e battery starts the supervisor). #3: DRAFT-0029 exists. Lexical within() on a chain entry with .. is harmless because every later entry is checked too. Side effect: a venv-link root without pyvenv.cfg now passes and fails in the jail with JailExitUnknown. Acceptable until DRAFT-0029: the policy it used to refuse was refused for the wrong reason, and the failure is the same one the ELF case already has. But no place an embedder reads states it (not the SPEC, not interpreter_refusal's docstring, not DRAFT-0029), so it is filed as DRAFT-0031. Full tier: five runs of one tree (branch claude/small-bugs, all four tasks), three green; two failed only test_interrupt_battery.py::test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost, a path this branch does not touch (signal_jail_pid1/_pid1_under); passes alone 3/3 and 8/8 in parallel. Filed as DRAFT-0030. No files changed by the check. This task's own recorded run is one of the two red ones.
<!-- SECTION:NOTES:END -->
