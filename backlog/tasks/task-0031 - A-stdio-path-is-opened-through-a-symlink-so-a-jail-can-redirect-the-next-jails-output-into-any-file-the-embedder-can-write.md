---
id: TASK-0031
title: >-
  A stdio path is opened through a symlink, so a jail can redirect the next
  jail's output into any file the embedder can write
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T03:31:00Z'
updated_date: '2026-11-03T03:59:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0028 (d98bc84). infra/supervisor/link.py _open_stdio opens stdout/stderr with O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC in brig's own process: no O_NOFOLLOW, and the 0600 mode applies only when the file is created. When an embedder names a stdio path inside a root the jail can write (a log beside the work, reused across runs), the jailed command can replace it with a symlink to, say, ~/.bashrc, and the next create_bwrap_jail appends that jail's output there with the embedder's permissions; stdin likewise reads any file the embedder can. Not measured.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A stdio path whose last component is a symlink is refused (O_NOFOLLOW or equivalent), or a stdio path under a writable root is refused at create, with an error saying what to do
- [x] #2 An e2e test plants the symlink from inside a jail and shows the next create does not write through it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at bb87cf97dfaf, test files: tests/e2e/test_cwd_stdio_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_cwd_stdio_battery.py -k writable_root` exited 1

(14 earlier lines omitted)
```text
            victim.write_text("before")
            (Path(root) / "out.txt").symlink_to(victim)
>           with pytest.raises(brig.PolicyStdioInWritableRoot) as refused:
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E           AttributeError: module 'brig' has no attribute 'PolicyStdioInWritableRoot'

tests/e2e/test_cwd_stdio_battery.py:86: AttributeError
=========================== short test summary info ============================
FAILED tests/e2e/test_cwd_stdio_battery.py::test_a_stdio_path_inside_a_writable_root_is_refused
1 failed, 4 deselected in 0.13s
```

Repro at 3a62030d4e6b, test files: tests/e2e/test_cwd_stdio_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_cwd_stdio_battery.py -k writable_root` exited 1

(26 earlier lines omitted)
```text
E           AssertionError: the jail's output went through the link
E           assert 'beforeappended\n' == 'before'
E             
E             - before
E             + beforeappended

tests/e2e/test_cwd_stdio_battery.py:95: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_cwd_stdio_battery.py::test_a_stdio_path_inside_a_writable_root_is_refused
1 failed, 4 deselected in 0.21s
```

Accepted 2026-11-03. Worker's report (Claude): fixed at 55336cd. Measured first: the committed repro (above) ran a jail whose stdout path was a link, inside the writable root, to a file outside it, and the jail's output was appended to that file ('beforeappended'). Fix: domain stdio_refusal refuses any named stdio path (but /dev/null) inside a writable root, raised as PolicyStdioInWritableRoot before anything starts; infra opens every stdio file with O_NOFOLLOW as well. The repro passes now (refused, the target untouched); unit cases cover the refusal; the cwd/stdio battery's own streams moved outside the writable root, as the refusal requires. uv run just done passes.

Check `uv run just done` exited 0

(251 earlier lines omitted)
```text
[2m03:44:32.283[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m03:44:32.288[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m03:44:32.303[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m03:44:34.333[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.12s
[2m03:44:34.336[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m03:44:34.339[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3s[39m[0m

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
INFO    -  Documentation built in 5.60 seconds

== architecture validate: PASS ==
[2m03:44:36.185[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m03:44:36.202[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m03:44:36.230[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m03:44:36.231[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m03:44:36.709[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m03:44:36.928[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m03:44:36.929[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 744ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Review 2026-11-03 (reviewer, not closed). Full gate passes. AC#2 met (e2e plants the link, next create refused, target untouched). AC#1 not met: the refusal is lexical, so a stdio path outside the writable roots that reaches one through a link in a parent directory is not refused, and O_NOFOLLOW covers only the last component. Measured: writable root R with R/logs, an outside link O/logs -> R/logs; jail 1 replaces R/logs with a link to victim dir V; jail 2 with stdout=O/logs/out.txt is accepted and V/out.txt becomes 'beforeappended'. Fix: check the stdio path's resolved parent (realpath) against the resolved writable roots, or open with openat2 RESOLVE_NO_SYMLINKS. Also not covered by design: a stdio path in a root another jail of the same embedder may write; brig cannot see that policy, so only no-symlink resolution (RESOLVE_NO_SYMLINKS on the whole path) closes it, or a documented embedder rule.

Repro at d9352822539a, test files: tests/e2e/test_cwd_stdio_battery.py; command: `uv run pytest -q -p no:cacheprovider tests/e2e/test_cwd_stdio_battery.py -k parent_link` exited 1

(28 earlier lines omitted)
```text
E            +  where True = exists()
E            +    where exists = (PosixPath('/tmp/tmp2671uobs') / 'out.txt').exists
E            +      where PosixPath('/tmp/tmp2671uobs') = Path('/tmp/tmp2671uobs')

tests/e2e/test_cwd_stdio_battery.py:137: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_cwd_stdio_battery.py::test_a_stdio_path_reaching_a_writable_root_through_a_parent_link_is_refused
1 failed, 5 deselected in 0.17s
```

Worker, 2026-11-03, on the review's finding (a stdio path whose parent links into a writable root): reproduced (repro above) and fixed at 8b42a6a. stdio_refusal now checks every path the stdio path's lookup passes through (infra.files.link_chain), so outside/logs/out.txt that goes through root/logs is refused (PolicyStdioInWritableRoot), though its text and its final target are outside the root. Besides, infra opens each stdio file one component at a time with O_PATH|O_DIRECTORY|O_NOFOLLOW and O_NOFOLLOW on the last, so a link swapped in after the check fails the start (JailSpawnFailed) instead of redirecting it. That no-link open is also what covers a stdio path in a root another jail of the same embedder may write, which brig cannot see. uv run just done passes.

Check `uv run just done` exited 0

(259 earlier lines omitted)
```text
[2m03:59:42.054[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:app-config[39m[0m
[2m03:59:42.056[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m03:59:42.076[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m03:59:44.175[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.25s
[2m03:59:44.178[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m03:59:44.181[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.1s[39m[0m

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
INFO    -  Documentation built in 5.82 seconds

== architecture validate: PASS ==
[2m03:59:45.917[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m03:59:45.938[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m03:59:45.974[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m03:59:45.975[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m03:59:46.549[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m03:59:46.811[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m03:59:46.811[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 896ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
