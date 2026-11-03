---
id: TASK-0042
title: >-
  A jail reopens its stdio files through /proc/self/fd with more rights than
  brig granted
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:15:00Z'
labels:
  - brig
  - stdio
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (demonstrated in real bwrap 0.9.0): a jail with no writable root opened /proc/self/fd/0 O_WRONLY|O_TRUNC and overwrote the host's stdin file, and opened /proc/self/fd/1 O_RDONLY to read the append-only stdout file, while the report said fs_write, fs_read and channel_exclusivity ENFORCED. The magic link reopens the inode and permission is checked on the file's mode for the same uid. INHERIT is affected too (an embedder's log file as stdout). Proposed: never hand the jail an fd on a host inode: pipes, pumped by the host to and from the files; count stdio as a shared medium under law 9.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No jail is handed an fd on a host inode for stdio: a PATH or INHERIT stdio reaches the jail as a pipe the host pumps to and from the file (or the embedder's own stream), so reopening /proc/self/fd/N reaches only the pipe
- [ ] #2 An e2e battery reopens each stdio fd through /proc/self/fd with a wider mode (truncate stdin's file, read the append-only stdout file) and fails if the host file changes or is read; recorded failing before the fix
- [ ] #3 Pumping ends with the jail: destroy_jail drains and closes the pumps, and a jail that never reads stdin or floods stdout cannot block the host past destroy (law 7)
- [ ] #4 The spec counts stdio among the media law 9 names, and channel_exclusivity's claim text says what stdio carries
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at 52685e6234f5, test files: tests/e2e/test_stdio_reopen_battery.py; command: `uv run pytest tests/e2e/test_stdio_reopen_battery.py` exited 1

(1 earlier lines omitted)
```text
============================= test session starts ==============================
platform linux -- Python 3.15.0b4, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/user/brig-pins
configfile: pyproject.toml
plugins: platformdirs-4.13.4
collected 2 items

tests/e2e/test_stdio_reopen_battery.py FF                                [100%]

=================================== FAILURES ===================================
___________ test_reopening_path_stdio_reaches_none_of_the_host_files ___________

    def test_reopening_path_stdio_reaches_none_of_the_host_files() -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as streams:
            stdin, stdout, stderr = (Path(streams) / name for name in ("in", "out", "err"))
            stdin.write_text("the host's input")
            stdout.write_text("EARLIER output\n")
            stderr.write_text("EARLIER log\n")
            jail = create_bwrap_jail(
                (sys.executable, "-I", "-c", _REOPEN),
                stdio=Stdio(stdin=str(stdin), stdout=str(stdout), stderr=str(stderr)),
            )
            try:
                code = run_jail(jail, timeout_s=15)
            finally:
                destroy_jail(jail)
            out, err, kept_in = stdout.read_text(), stderr.read_text(), stdin.read_text()
        assert "control|the host's input" in out, f"the control did not get through: {out!r}"
>       assert code != 9, "the jail read the stdout file's earlier contents through /proc/self/fd/1"
E       AssertionError: the jail read the stdout file's earlier contents through /proc/self/fd/1
E       assert 9 != 9

tests/e2e/test_stdio_reopen_battery.py:66: AssertionError
______ test_reopening_inherited_stdio_reaches_none_of_the_embedders_files ______

    def test_reopening_inherited_stdio_reaches_none_of_the_embedders_files() -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as streams:
            stdout, stderr = Path(streams) / "out", Path(streams) / "err"
            stdout.write_text("EARLIER output\n")
            stderr.write_text("EARLIER log\n")
            with stdout.open("a") as out_file, stderr.open("a") as err_file:
                embedder = subprocess.run(
                    (sys.executable, "-c", _EMBEDDER, _REOPEN),
                    stdin=subprocess.DEVNULL,
                    stdout=out_file,
                    stderr=err_file,
                    timeout=60,
                )
            out, err = stdout.read_text(), stderr.read_text()
        assert "control|" in out, f"the control did not get through: {out!r} {err!r}"
>       assert embedder.returncode != 9, "the jail read the embedder's stdout file through its fd"
E       AssertionError: the jail read the embedder's stdout file through its fd
E       assert 9 != 9
E        +  where 9 = CompletedProcess(args=('/home/user/brig-pins/.venv/bin/python', '-c', '\nimport sys\nfrom brig import create_bwrap_jai... OSError:\n        pass\nos.write(1, ("control|" + received).encode())\nsys.exit(9 if leaked else 0)\n'), returncode=9).returncode

tests/e2e/test_stdio_reopen_battery.py:101: AssertionError
=========================== short test summary info ============================
FAILED tests/e2e/test_stdio_reopen_battery.py::test_reopening_path_stdio_reaches_none_of_the_host_files
FAILED tests/e2e/test_stdio_reopen_battery.py::test_reopening_inherited_stdio_reaches_none_of_the_embedders_files
============================== 2 failed in 0.40s ===============================
```

Check `uv run just done` exited 0

(270 earlier lines omitted)
```text
[2m18:15:13.590[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m18:15:13.598[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m18:15:13.600[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m18:15:15.830[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.33s
[2m18:15:15.852[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m18:15:15.855[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.2s[39m[0m

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
INFO    -  Documentation built in 6.06 seconds

== architecture validate: PASS ==
[2m18:15:17.611[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m18:15:17.628[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m18:15:17.654[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m18:15:17.655[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m18:15:18.232[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m18:15:18.539[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m18:15:18.539[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 929ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 50 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
