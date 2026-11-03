---
id: TASK-0025
title: >-
  A symlink at a write deny's or mask's path protects its target, not the path,
  so the command can replace it
status: Done
assignee:
  - '@claude'
created_date: '2026-11-03T03:06:00Z'
updated_date: '2026-11-03T03:22:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0024.01 (c4ef292). infra/files.py kinds() follows links, and compile_mounts emits --ro-bind P P (or /dev/null / empty_dir onto P) for a deny or mask at P. A mount onto a symlink lands on the link's target; the link itself stays an ordinary entry in the writable root. A command (or an earlier jail sharing the root) that makes P a symlink, e.g. <root>/.git/hooks -> <root>/elsewhere, can then unlink P inside the jail and create a real directory there that it writes freely, defeating the deny; the source side also follows the link on the host, so a link to a path outside every root binds that target into the jail. Not measured by the reviewer (the review hook blocks scratch runs); measure against real bwrap first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A deny or mask whose path is a symlink is refused, or compiled so the path itself cannot be written, created or read, with the decision saying which
- [x] #2 An e2e test plants a symlink at a deny path inside a writable root and shows the command can neither write through it nor replace it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal. Measured before any change (bubblewrap 0.9.0, as root): writable root W holding hooks -> real (a symlink), write deny W/hooks; the command unlinked W/hooks, made a directory there and wrote W/hooks/pre-commit, exit 0, and the host's W/hooks is now a real directory. Confirmed: the deny protects the link's target, not the path.

Repro at b3ca718d3b4c, test files: tests/e2e/test_fs_policy_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_fs_policy_battery.py -k through_a_link` exited 2

(9 earlier lines omitted)
```text
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/e2e/test_fs_policy_battery.py:50: in <module>
    from brig import (
E   ImportError: cannot import name 'PolicyPathThroughLink' from 'brig' (/home/user/brig/src/brig/__init__.py)
=========================== short test summary info ============================
ERROR tests/e2e/test_fs_policy_battery.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.24s
```

Repro at cf160a7af541, test files: tests/e2e/test_fs_policy_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_fs_policy_battery.py -k through_a_link` exited 1

(17 earlier lines omitted)
```text
>           with pytest.raises(brig.PolicyPathThroughLink) as refused:
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^
E           AttributeError: module 'brig' has no attribute 'PolicyPathThroughLink'

tests/e2e/test_fs_policy_battery.py:551: AttributeError
=========================== short test summary info ============================
FAILED tests/e2e/test_fs_policy_battery.py::test_a_deny_reached_through_a_link_inside_a_writable_root_is_refused
1 failed, 13 deselected in 0.12s
```

Worker's report (Claude, 2026-11-03). Fixed at 0dc45c0. infra.files.facts returns each policy path's kind and realpath; paths.refusal takes them (HostPath) and refuses with ThroughLink any entry (root, deny or mask) inside a writable root whose resolved path is not the root's resolved path plus the rest of the entry: a link between them. A link above the writable root (which the command cannot change) refuses nothing. Raised as PolicyPathThroughLink(path, root) before anything is created. Tests: the e2e repro above (now passing: create_bwrap_jail raises, the link is untouched), unit refusal cases for a link inside a root and a link above it. uv run just done passes (recorded on TASK-0024.02, same tree).

Review (reviewer, 2026-11-03): not closed. AC2 ticked: the e2e plants a hooks link inside a writable root and the jail is refused before anything runs, the link left in place (a refusal means no command ever writes through or replaces it). AC1 not met: the code refuses (ThroughLink, raised as PolicyPathThroughLink), but the criterion asks that the decision say which, and decision-0007 does not mention links: item 2 still lists only the not-absolute and mask-hides refusals, and neither the RootAbsent nor the ThroughLink refusal appears in it or in docs/spec. To close: add both refusals to decision-0007 item 2 (and the SPEC's refusal list), with the reason (a mount onto a link lands on its target). Residual, low: the check and the mount are separate moments, so something sharing the writable root (another jail) could swap a directory for a link between them.

Worker, 2026-11-03: decision-0007 item 2 now records both refusals and why (a mount onto a link lands on its target; the link stays replaceable), with the check-to-mount window noted; the SPEC's domain section lists all four refusals. The driver's docstring now says it is the shared interpreter.

Check `uv run just done` exited 0

(247 earlier lines omitted)
```text
[2m03:21:38.084[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m03:21:38.089[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m03:21:38.109[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m03:21:40.106[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.14s
[2m03:21:40.109[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m03:21:40.113[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 2.9s[39m[0m

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
INFO    -  Documentation built in 5.35 seconds

== architecture validate: PASS ==
[2m03:21:41.901[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m03:21:41.919[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m03:21:41.948[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m03:21:41.948[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m03:21:42.503[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m03:21:42.728[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m03:21:42.730[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 829ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Review (reviewer, 2026-11-03): closed. uv run just done passes (full tier, recorded). AC1 now met: 2b20c18 records in decision-0007 item 2 and the SPEC that an entry reached through a link inside a writable root is refused (not followed) and why, plus the absent-root refusal. AC2 ticked earlier. Residual check-to-mount window remains as noted in the decision; low, no task.
<!-- SECTION:NOTES:END -->
