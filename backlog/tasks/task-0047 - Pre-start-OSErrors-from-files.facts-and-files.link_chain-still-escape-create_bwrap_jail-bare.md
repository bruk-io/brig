---
id: TASK-0047
title: >-
  Pre-start OSErrors from files.facts and files.link_chain still escape
  create_bwrap_jail bare
status: Done
assignee: []
created_date: '2026-11-03T19:22:00Z'
updated_date: '2026-11-03T19:52:00Z'
labels:
  - brig
  - errors
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0046's worker, confirmed in review (2026-11-03). src/brig/infra/files.py: facts() catches only FileNotFoundError/NotADirectoryError around os.stat, so a policy path the embedder cannot search (PermissionError) or a symlink loop (ELOOP) crosses create_bwrap_jail as a bare OSError, past the driver-exception-boundary rule. link_chain() calls os.readlink, which can raise if the link changes underneath it (a race). Related: in bwrap._supervisor_path, assemble.assembled_source() runs inside the write's try, so a broken install's read error reads as StateDirectoryWriteFailed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every OSError files.facts and files.link_chain can raise during create_bwrap_jail crosses as one of presentation/errors.py's types, with the OSError as its cause; integration tests pin each; recorded failing before the fix
- [x] #2 Reading brig's own supervisor source failing is not reported as StateDirectoryWriteFailed
- [x] #3 A PermissionError or ELOOP from files.facts, and an OSError from files.link_chain's readlink, cross create_bwrap_jail as one of presentation/errors.py's types with the OSError as cause; integration or e2e tests make each happen for real; recorded failing before the fix
- [x] #4 Reading brig's own supervisor source sits outside the script write's error handling, so a broken install is not reported as StateDirectoryWriteFailed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).

Repro at a7c18b06b000, test files: tests/integration/test_create_inspection_errors.py; command: `uv run pytest tests/integration/test_create_inspection_errors.py -q` exited 1

(59 earlier lines omitted)
```text
tests/integration/test_create_inspection_errors.py:129: AssertionError
_ test_a_stdio_path_through_a_link_brig_cannot_read_crosses_as_brigs_own_error _

work = PosixPath('/tmp/tmpd3nm_tnq')

    def test_a_stdio_path_through_a_link_brig_cannot_read_crosses_as_brigs_own_error(
        work: Path,
    ) -> None:
        """The stdio path goes through root's `/proc/<pid>/cwd`, and the embedder is `nobody`: the
        link is there, and reading where it leads is refused (`EACCES`)."""
        _needs_root()
    
        outcome = _create_in_child(work, "readlink")
    
        assert outcome["uid"] == _NOBODY
>       _assert_crossed_as_brigs_own(outcome)

tests/integration/test_create_inspection_errors.py:177: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

outcome = {'raised': True, 'uid': 65534, 'type': 'PermissionError', 'module': 'builtins', ...}

    def _assert_crossed_as_brigs_own(outcome: dict[str, object]) -> None:
        """The create failed with one of `presentation/errors.py`'s types, exported by `brig`, whose
        `__cause__` is the host's `OSError`."""
        assert outcome["raised"] is True
>       assert outcome["is_oserror"] is False, f"a bare {outcome['type']} crossed the API"
E       AssertionError: a bare PermissionError crossed the API
E       assert True is False

tests/integration/test_create_inspection_errors.py:129: AssertionError
_ test_a_supervisor_source_that_cannot_be_read_is_not_a_state_directory_failure _

work = PosixPath('/tmp/tmp8khie5_4')

    def test_a_supervisor_source_that_cannot_be_read_is_not_a_state_directory_failure(
        work: Path,
    ) -> None:
        """brig is imported from a copy whose supervisor program is then deleted: the failure is
        brig's own error, not `StateDirectoryWriteFailed`, and no script is left in the state
        directory."""
        shutil.copytree(
            _ROOT / "src" / "brig",
            work / "site" / "brig",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    
        outcome = _create_in_child(work, "source")
    
        _assert_crossed_as_brigs_own(outcome)
>       assert outcome["type"] != "StateDirectoryWriteFailed"
E       AssertionError: assert 'StateDirectoryWriteFailed' != 'StateDirectoryWriteFailed'

tests/integration/test_create_inspection_errors.py:197: AssertionError
=========================== short test summary info ============================
FAILED tests/integration/test_create_inspection_errors.py::test_a_policy_path_the_embedder_cannot_search_crosses_as_brigs_own_error
FAILED tests/integration/test_create_inspection_errors.py::test_a_policy_path_that_is_a_link_loop_crosses_as_brigs_own_error
FAILED tests/integration/test_create_inspection_errors.py::test_a_stdio_path_through_a_link_brig_cannot_read_crosses_as_brigs_own_error
FAILED tests/integration/test_create_inspection_errors.py::test_a_supervisor_source_that_cannot_be_read_is_not_a_state_directory_failure
4 failed in 0.62s
```

Check `uv run just done` exited 1

(434 earlier lines omitted)
```text
[2m19:33:40.690[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m19:33:40.716[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m19:33:42.718[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.19s
[2m19:33:42.722[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m19:33:42.725[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3s[39m[0m

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
INFO    -  Documentation built in 5.88 seconds

== architecture validate: PASS ==
[2m19:33:44.516[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m19:33:44.532[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m19:33:44.559[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m19:33:44.559[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m19:33:45.119[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m19:33:45.463[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m19:33:45.463[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 948ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: 1 step(s) failed: e2e tests
error: recipe `done` failed on line 71 with exit code 1
```

Check `uv run just done` exited 0

(294 earlier lines omitted)
```text
[2m19:40:37.223[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m19:40:37.230[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m19:40:37.273[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m19:40:39.410[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.29s
[2m19:40:39.413[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m19:40:39.416[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.2s[39m[0m

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
INFO    -  Documentation built in 5.90 seconds

== architecture validate: PASS ==
[2m19:40:41.120[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m19:40:41.137[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m19:40:41.178[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m19:40:41.179[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m19:40:41.735[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m19:40:42.030[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m19:40:42.030[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 911ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Worker, 2026-11-03: repro a7c18b0, fix 5c12ea4.

- Repro (tests/integration/test_create_inspection_errors.py): four child Pythons, each with its own BRIG_HOME. EACCES: a policy path beneath a 0700 root-owned directory, the child dropped to nobody (65534) after its imports (the interpreter lives under /root, so it cannot exec as nobody). ELOOP: a policy path in a two-link loop. link_chain's readlink: a stdio path through the root parent's /proc/<pid>/cwd, the child as nobody: lstat says it is a link and readlink is refused (EACCES), deterministic, no race needed. Broken install: brig imported from a copy of src/brig whose supervisor/program.py is deleted once imported. Each failed on an assertion about what crossed (a bare PermissionError/OSError; StateDirectoryWriteFailed).
- Types: no existing type fits, so two are added. PolicyPathUninspectable(path) for a path the policy or stdio names, or the interpreter, that the host will not let brig inspect (facts' stat or link_chain's readlink); path is the caller's path, not the link component. SupervisorSourceUnreadable() for brig's own supervisor source; the OSError cause names the file. JailSpawnFailed was considered for the second and rejected: nothing was spawned, and its message does not tell the embedder to reinstall.
- Fix: the bwrap driver calls files.facts per path and files.link_chain through _facts/_link_chain, each translating OSError with the OSError as __cause__. _supervisor_path reads assembled_source() before making the file, outside the write's try. Every other driver call into infra.files was checked (link_count, first_link, own_regular_file swallow their OSErrors). infra.files docstrings now say what propagates; docs/spec/index.md names both types and the test that holds them.
- Public API change: brig exports PolicyPathUninspectable and SupervisorSourceUnreadable (additive). An embedder that caught bare OSError from create_bwrap_jail for these cases now gets these types instead.
- First full-tier run (eb2d372's record) failed one e2e test, which record-check's tail did not keep; e2e passed in five reruns and in the second full-tier record (688d0fd), so it reads as an intermittent e2e flake unrelated to this change (the change only alters failures before anything starts). Not identified.

Check `uv run just done` exited 0

(294 earlier lines omitted)
```text
[2m19:43:38.030[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m19:43:38.032[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m19:43:38.082[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m19:43:40.020[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.12s
[2m19:43:40.023[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m19:43:40.025[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 2.9s[39m[0m

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
INFO    -  Documentation built in 5.68 seconds

== architecture validate: PASS ==
[2m19:43:41.686[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m19:43:41.702[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m19:43:41.740[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m19:43:41.741[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m19:43:42.254[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m19:43:42.612[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m19:43:42.613[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 928ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 51 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Reviewer, 2026-11-03: closed. Every criterion met. Repros are real: two children drop to uid 65534 (asserted), ELOOP comes from a real two-link loop, the readlink of root's /proc/<pid>/cwd is refused EACCES (asserted errno), and the broken install is a copied brig with program.py deleted after import (asserts ENOENT and no script left behind); all four failed at a7c18b0 on what crossed. Fix wraps facts/link_chain per path with the OSError as __cause__, and reads assembled_source() before the write's try. PolicyPathUninspectable and SupervisorSourceUnreadable each say what to do (make the path searchable / leave it out; reinstall brig), are exported, and are in docstrings per decision-0001 rule 13. Full tier rerun by the reviewer passed (e2e 145 passed, 4 skipped), no files changed by the check. The worker's first full-tier e2e failure stays unnamed: record-check kept only the tail and neither later full run reproduced it, so it is not known whether it is test_interrupt_battery.py::test_an_interrupt_sent_as_soon_as_the_jail_exists_is_not_lost; no draft filed without a name or output. Minor, not filed: rule 13 says context goes on with add_note at infra's edge, and this change chains the cause in presentation instead, which the criteria asked for.
<!-- SECTION:NOTES:END -->
