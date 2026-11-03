---
id: TASK-0047
title: >-
  Pre-start OSErrors from files.facts and files.link_chain still escape
  create_bwrap_jail bare
status: To Do
assignee: []
created_date: '2026-11-03T19:22:00Z'
updated_date: '2026-11-03T19:27:00Z'
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
- [ ] #1 Every OSError files.facts and files.link_chain can raise during create_bwrap_jail crosses as one of presentation/errors.py's types, with the OSError as its cause; integration tests pin each; recorded failing before the fix
- [ ] #2 Reading brig's own supervisor source failing is not reported as StateDirectoryWriteFailed
- [ ] #3 A PermissionError or ELOOP from files.facts, and an OSError from files.link_chain's readlink, cross create_bwrap_jail as one of presentation/errors.py's types with the OSError as cause; integration or e2e tests make each happen for real; recorded failing before the fix
- [ ] #4 Reading brig's own supervisor source sits outside the script write's error handling, so a broken install is not reported as StateDirectoryWriteFailed
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
<!-- SECTION:NOTES:END -->
