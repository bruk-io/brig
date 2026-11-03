---
id: TASK-0042
title: >-
  A jail reopens its stdio files through /proc/self/fd with more rights than
  brig granted
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:05:00Z'
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
<!-- SECTION:NOTES:END -->
