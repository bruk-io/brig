---
id: TASK-0052
title: >-
  A policy without the interpreter's ELF loader and libraries passes
  interpreter_refusal and fails in bwrap with execvp No such file
status: To Do
assignee: []
created_date: '2026-11-03T03:46:00Z'
updated_date: '2026-11-04T14:06:00Z'
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
- [ ] #1 A policy that lacks the interpreter's ELF interpreter or a shared library it needs is refused before bwrap with a typed error naming the path
- [ ] #2 A policy that bwrap can start the supervisor under is not refused
- [ ] #3 link_chain resolves '..' after a link as the kernel does
- [ ] #4 infra.files.link_chain resolves a/link/../b as the kernel does (the link first, then ..), not by normalising .. as text; a tmp-tree test pins it; repro test recorded failing
- [ ] #5 A policy whose readable root is the venv's python3 link itself is not refused by interpreter_refusal
- [ ] #6 The ELF loader and DT_NEEDED half is split out as a design draft of its own
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
<!-- SECTION:NOTES:END -->
