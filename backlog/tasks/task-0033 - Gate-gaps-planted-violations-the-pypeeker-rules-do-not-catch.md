---
id: TASK-0033
title: 'Gate gaps: planted violations the pypeeker rules do not catch'
status: Done
assignee:
  - '@claude'
created_date: '2026-11-02T17:23:00Z'
updated_date: '2026-11-03T05:07:00Z'
labels:
  - size-3
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by an architecture review, 2026-11-02, at 739dd94. 30 violations planted in a scratch copy: the layer, slice and test-layer rules caught every crossing tried. These exited 0: `pytest.MonkeyPatch.context()` and `setattr(brig, ...)` in tests (rule: no patching); a fake dataclass in `tests/e2e`; `os.write(1|2, ...)` and `logging` in infra or presentation (rule 14, one writer); `list`/`dict` fields on a frozen domain dataclass (rule 8).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each planted violation above fails the gate, with a pypeeker rule test that plants it
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. brig-no-patching (pypeeker_rules/brig.py): the import part also refuses pytest.MonkeyPatch and _pytest.monkeypatch; a new references part refuses pytest.MonkeyPatch reached through an import of pytest (pytest.MonkeyPatch.context(), an annotation); a new imports part, through a trait anchored on the import, refuses setattr/delattr whose first argument is a name the file imports (setattr(brig, ...)); a references part refuses an attribute assignment through an imported name (brig.x = ...); a symbols part refuses a class named as a double (fake, stub, mock, dummy, spy as a word of its name) outside tests/integration/.
2. brig-one-writer: a part refusing os.write/os.writev called through an import of os, or imported by name, outside the allow list (the supervisor's wire); a part refusing any import of logging under src/brig (no allow: the library logs nothing, and the wire writes its own JSON); the stream part also catches a chain that starts with sys.stdout/sys.stderr (sys.stdout.buffer.write).
3. A new rule, brig-frozen-data (decision-0001 rule 8): a field of a @dataclass class under src/brig/domain whose annotation names a mutable container (list, dict, set, bytearray, their typing aliases, deque, defaultdict ...), ClassVar excluded. Enabled in pyproject.toml with root src/brig/domain.
4. Every message says what to do instead. Each new part gets a planted-violation test and a clean case in pypeeker_rules/tests/test_brig_rules.py.
5. just gates over the real code; any finding in real code is fixed in the code, never in the rule or an allow list.
### Risks
- The DSL sees no call arguments: os.write's fd cannot be read, so every os.write outside the wire is refused (brig's other writes go through file objects today). setattr's first argument is found as the first reference after the call's name in the same scope: a first argument holding no reference reads as clean (a false negative, never a false positive).
- A double is recognised by its name only; an unnamed double (a port implementation with nothing real behind it, a SimpleNamespace) is not seen.
- Rule 8's annotation match is textual over the binder's raw annotation; an alias of list imported under another name is not seen.
### Proof
- uv run just test-pypeeker-rules: every new part fires on its planted violation and stays quiet on its clean case.
- uv run just gates green on the real tree; uv run just done green.
- record-check --tier full on the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Worker's report (@claude, commit e13cec1)

What changed: pypeeker_rules/brig.py (two rules extended, one added), pypeeker_rules/tests/test_brig_rules.py (23 new tests), pyproject.toml (brig-frozen-data enabled, root src/brig/domain). Every new message says what to do instead. No existing rule or allow list was weakened; the real tree already passed every new part, so no code changed.

Each planted violation, its rule part and its tests:
- pytest.MonkeyPatch.context(): brig-no-patching _monkeypatch_class_uses (MonkeyPatch read through an import of pytest, aliased too) and _MOCK_MODULES gaining pytest.MonkeyPatch and _pytest.monkeypatch (from-import). Tests: ..._fires_on_monkeypatch_context, ..._through_an_aliased_pytest, ..._importing_monkeypatch_by_name; clean: ..._accepts_other_pytest_attributes.
- setattr(brig, ...): _setattr_on_imports, a trait anchored on the import: is it the first argument of a setattr/delattr call (the first reference after the call's name in its scope). Also _attribute_writes_on_imports for brig.x = f. Tests: ..._setattr_of_an_imported_module, ..._multi_line_delattr_of_an_import, ..._attribute_assigned_through_an_import; clean: ..._accepts_setattr_on_a_local_object.
- A fake dataclass in tests/e2e: _doubles_outside_integration, a class with fake/stub/mock/dummy/spy as a word of its name outside tests/integration/. Tests: ..._fake_dataclass_in_e2e, ..._private_stub_in_unit; clean: ..._accepts_a_fake_in_integration_and_a_real_helper_in_e2e.
- os.write(1|2, ...): brig-one-writer _fd_write_calls and _fd_write_imports. Tests: ..._os_write_to_stdout_in_infra, ..._to_stderr_through_an_alias, ..._imported_by_name; clean: ..._accepts_the_wires_os_write_and_other_os_calls. Also sys.stdout.buffer.write (..._stdout_buffer_write).
- logging in infra or presentation: _logging_imports, with no allow list. Tests: ..._logging_in_infra, ..._logging_in_presentation_by_name, ..._logging_even_in_the_supervisors_wire.
- list/dict fields on a frozen domain dataclass: new rule brig-frozen-data. Tests: ..._list_field, ..._dict_field, ..._list_nested_in_a_tuple; clean: ..._accepts_tuples_frozendicts_and_non_fields.

What the DSL cannot express, and so is narrower than the review's wording:
- The index records no call arguments. os.write's descriptor cannot be read, so every os.write/os.writev under src/brig outside the allow list is refused, not only fd 1 and 2. Today only the supervisor's wire uses it.
- A double is known only by its name. A double named otherwise is not seen, such as a port implemented with nothing real behind it or a SimpleNamespace.
- A patch of a local object's method is not seen.
- Rule 8's match is over the annotation text. A mutable type imported under another name is not seen.

Shapes in the real tree for the owner to judge (not flagged, not changed): tests/e2e/test_supervisor_assemble.py builds fake_sys, a SimpleNamespace double in e2e. tests/integration/test_policy_refusal.py assigns directories.create = stop, patching a fake's method. decision-0001 rule 8 still names only mypy; its enforcement line could add brig-frozen-data.

Gate: uv run just done, every step passed (lint, typecheck, gates, 48 pypeeker rule tests, unit, integration x2, e2e, docs, architecture validate and lint).

Check `uv run just done` exited 0

(254 earlier lines omitted)
```text
[2m04:09:03.112[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m04:09:03.117[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:09:03.136[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:09:05.660[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.67s
[2m04:09:05.664[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-gates/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:09:05.667[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.5s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig-gates/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-gates/docs
INFO    -  Documentation built in 6.21 seconds

== architecture validate: PASS ==
[2m04:09:07.461[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:09:07.485[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-gates/docs/architecture[0m
[2m04:09:07.534[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:09:07.535[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:09:08.083[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m04:09:08.315[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m04:09:08.315[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 855ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Check `uv run just done` exited 1

(267 earlier lines omitted)
```text
[2m04:11:40.824[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:11:40.846[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:11:43.178[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.53s
[2m04:11:43.181[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:11:43.185[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.4s[39m[0m

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
INFO    -  Documentation built in 6.12 seconds

== architecture validate: PASS ==
[2m04:11:45.061[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:11:45.077[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m04:11:45.116[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:11:45.117[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:11:45.661[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m04:11:45.906[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m04:11:45.906[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 847ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: 1 step(s) failed: gates
error: recipe `done` failed on line 71 with exit code 1
```

Review (reviewer, 2026-11-03): NOT CLOSED. Full gate record-check --tier full: just done fails at gates. brig-no-patching's attribute-write part fires on tests/e2e/test_report_battery.py:117-118 (os.environ[...] = ...). That file was there at 282295b, so the worker's green run was measured on another tree (/home/user/brig-gates). The plan's step 5 says real-code findings are fixed in the code; filed as a draft (brig-no-patching fails the gate on test_report_battery's os.environ writes). Everything else holds: each listed violation has a rule test that plants it and passes, every message says what to do instead, and the diff against 282295b^ weakens nothing (old messages reworded with a fix added; the stream match goes from exact to prefix, which is broader; _MOCK_MODULES only grows; pyproject only adds brig-frozen-data). I could not plant the violations in a scratch copy: the review hook refuses copying the repository, so the rule tests are the evidence. The worker's two flagged shapes both break rule 5 as written (a SimpleNamespace double in e2e; a fake's method replaced, where fail_create already does the job). Filed as a draft (Two test doubles that break decision-0001 rule 5). AC #1 was already ticked on the board before this review; I left it alone.

Worker, 2026-11-03, on the latest review, fixed at fe3f40d (see its message for each). TASK-0021: every mounted deny/mask caps fs_write/fs_read at BEST_EFFORT, with e2e cases for a host rename over a mask under a read-only root (this container keeps the mask, the reviewer's kernel did not: the grade allows for both) and a write at a deny. TASK-0034: PolicyStdioThroughLink names the link (infra.files.first_link). TASK-0035: an existing stdio path must be a regular file the embedder owns (PolicyStdioNotOwnFile; checked again once opened); e2e cases for another user's 0666 file and /dev/zero. TASK-0033: the gate failure came from the report battery writing os.environ; it now passes its environment as data; the rule's message names item writes. TASK-0036: law 9 counts argv as a shared medium again and says nothing tests it yet. uv run just done passes at fe3f40d.

Check `uv run just done` exited 0

(258 earlier lines omitted)
```text
[2m05:05:56.832[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m05:05:56.846[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m05:05:56.898[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m05:05:58.898[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.21s
[2m05:05:58.906[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m05:05:58.914[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.3s[39m[0m

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
INFO    -  Documentation built in 6.11 seconds

== architecture validate: PASS ==
[2m05:06:01.014[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m05:06:01.040[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m05:06:01.126[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m05:06:01.127[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m05:06:01.899[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m05:06:02.316[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m05:06:02.317[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 1.3s[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 50 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Review (reviewer, 2026-11-03): CLOSED. record-check --tier full: uv run just done passed, gates included. The earlier blocker is fixed: tests/e2e/test_report_battery.py no longer writes os.environ (it hands the environment over as data; the only os.environ left is read-only, inside the jailed script's text). No new findings. The two drafts from the last review stay as filed.
<!-- SECTION:NOTES:END -->
