---
id: TASK-0026
title: >-
  compile_mounts keeps an absent deny or mask that sits under a read-only root
  nested in a writable one, which bwrap cannot mount
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T03:06:00Z'
updated_date: '2026-11-03T03:16:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0024.01 (c4ef292). _kept() keeps an absent deny/mask when any writable root covers it, but decision-0007 item 4's own reason for dropping absent entries is that bwrap cannot make a mountpoint on a read-only mount. With writable=(/w,), readable=(/w/ro,) (or write_denies=(/w/d,)) and an absent mask or deny at /w/ro/x, the most specific covering root is read-only, the entry is kept, and bwrap must mkdir /w/ro/x inside a read-only bind, so the jail fails to start (fails closed, as JailExitUnknown). Related refusal gap: a readable or writable root that does not exist on the host is not refused and reaches bwrap as a missing source.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An absent entry is kept only when the most specific root or deny covering it is writable, with a unit case for a readable root and a write deny nested in a writable root
- [ ] #2 A root absent on the host is refused before anything is created, or the decision says why it is compiled
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at 2c5fe1a3587d, test files: tests/e2e/test_fs_policy_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_fs_policy_battery.py -k 'nested_read_only or read_only_root_inside or root_absent'` exited 2

(7 earlier lines omitted)
```text
/root/.local/share/uv/python/cpython-3.15.0b4-linux-x86_64-gnu/lib/python3.15/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/e2e/test_fs_policy_battery.py:50: in <module>
    from brig import (
E   ImportError: cannot import name 'PolicyPathThroughLink' from 'brig' (/home/user/brig/src/brig/__init__.py)
=========================== short test summary info ============================
ERROR tests/e2e/test_fs_policy_battery.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.16s
```

Repro at f19782dd42be, test files: tests/e2e/test_fs_policy_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_fs_policy_battery.py -k 'read_only_root_inside or root_absent'` exited 1

(83 earlier lines omitted)
```text
        """TASK-0026: a root must exist to be mounted; refused before anything starts, naming it."""
        with _fresh_tmp_dir() as root:
            missing = f"{root}/not-there"
>           with pytest.raises(brig.PolicyRootAbsent) as refused:
                               ^^^^^^^^^^^^^^^^^^^^^
E           AttributeError: module 'brig' has no attribute 'PolicyRootAbsent'

tests/e2e/test_fs_policy_battery.py:583: AttributeError
=========================== short test summary info ============================
FAILED tests/e2e/test_fs_policy_battery.py::test_an_absent_entry_under_a_read_only_root_inside_a_writable_one_needs_no_mount
FAILED tests/e2e/test_fs_policy_battery.py::test_a_root_absent_on_the_host_is_refused
2 failed, 12 deselected in 0.11s
```

Worker's report (Claude, 2026-11-03). Fixed at 0dc45c0. compile_mounts keeps an absent deny or mask only where the most specific entry above it is a writable root (_governing_role); under a readable root or a present deny nested in a writable root it is dropped (the command cannot create it, bwrap could not mount it). refusal refuses a readable or writable root that is absent on the host (RootAbsent, raised as PolicyRootAbsent). Tests: the e2e repros above (both pass now: the jail starts and writes beside; the absent root is refused), a unit case for the nested read-only parent and one for the absent root. uv run just done passes (recorded on TASK-0024.02, same tree).

Check `uv run just done` exited 0

(251 earlier lines omitted)
```text
[2m03:15:59.446[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m03:15:59.586[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m03:15:59.654[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m03:16:04.195[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 4.95s
[2m03:16:04.202[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m03:16:04.205[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 7.1s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig/docs
INFO    -  Documentation built in 10.39 seconds

== architecture validate: PASS ==
[2m03:16:07.440[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m03:16:07.500[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m03:16:07.695[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m03:16:07.696[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m03:16:09.247[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m03:16:09.804[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m03:16:09.810[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 2.3s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
