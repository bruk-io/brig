---
id: TASK-0046
title: >-
  Errors that still escape create_bwrap_jail untranslated, and a dismantle that
  can mask the step's error
status: To Do
assignee: []
created_date: '2026-11-03T18:58:00Z'
updated_date: '2026-11-03T19:08:00Z'
labels:
  - brig
  - errors
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0044/0045's worker and review (2026-11-03): (1) writing the supervisor script (_supervisor_path) and state_dir.ensure_empty can raise a bare OSError out of create_bwrap_jail, past the driver-exception-boundary rule; (2) dismantle's docstring says it raises nothing, but an OSError from run(operations.destroy) or supervisors.close would escape and hide the failed step's own error; (3) if run(operations.create) itself raises after bwrap has spawned, process is still None and the kill ladder is skipped (true before TASK-0044 too).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every OSError create_bwrap_jail can raise before the start (writing the supervisor script, preparing the state directory) crosses as one of presentation/errors.py's types, with the OSError as its cause; integration tests with fakes pin each; recorded failing before the fix
- [ ] #2 dismantle never hides the failed step's error: a teardown or close failure inside it is attached to the step's error (add_note or a chained cause) or raises JailTeardownFailed, and its docstring says which
- [ ] #3 If operations.create raises after bwrap has spawned, the spawned process is still torn down (the create effect hands back what it spawned, or the driver reaps by pidfd); a test with a fake that spawns then fails pins it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).

Repro at e14be84ae900, test files: tests/integration/test_create_error_edges.py; command: `uv run pytest tests/integration/test_create_error_edges.py -q` exited 1

(98 earlier lines omitted)
```text
E       AssertionError: PermissionError(1, "fake host: the teardown's signal was refused")
E       assert False
E        +  where False = isinstance(PermissionError(1, "fake host: the teardown's signal was refused"), JailTeardownFailed)
E        +    where PermissionError(1, "fake host: the teardown's signal was refused") = <ExceptionInfo PermissionError(1, "fake host: the teardown's signal was refused") tblen=5>.value

tests/integration/test_create_error_edges.py:141: AssertionError
____________ test_a_close_that_raises_does_not_hide_the_steps_error ____________

    def test_a_close_that_raises_does_not_hide_the_steps_error() -> None:
        """The attach fails, the teardown reads the group gone after TERM, and closing the
        supervisor's pipe raises: the attach's own `PlaceholdersFailed` still propagates, with the
        close's failure attached to it, and the placeholders are released."""
        processes = FakeProcesses(alive_checks=1)
        supervisors = FakeSupervisors(fail_close=True)
        placeholders = FakePlaceholders(fail_attach=True)
    
        with pytest.raises(BaseException) as raised:
            create_bwrap_jail(
                ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
            )
    
>       assert isinstance(raised.value, PlaceholdersFailed), repr(raised.value)
E       AssertionError: OSError(5, "fake host: the supervisor's pipe could not be closed")
E       assert False
E        +  where False = isinstance(OSError(5, "fake host: the supervisor's pipe could not be closed"), PlaceholdersFailed)
E        +    where OSError(5, "fake host: the supervisor's pipe could not be closed") = <ExceptionInfo OSError(5, "fake host: the supervisor's pipe could not be closed") tblen=4>.value

tests/integration/test_create_error_edges.py:163: AssertionError
___ test_a_start_that_spawned_then_failed_tears_the_spawned_supervisor_down ____

    def test_a_start_that_spawned_then_failed_tears_the_spawned_supervisor_down() -> None:
        """The port's start spawned the supervisor and then failed: `JailSpawnFailed` still
        propagates, and before it does the spawned supervisor's group was verified, sent TERM,
        verified gone, its pid released and its pipe closed."""
        processes = FakeProcesses(alive_checks=1)
        supervisors = FakeSupervisors(fail_after_start=True)
        placeholders = FakePlaceholders()
    
        with pytest.raises(BaseException) as raised:
            create_bwrap_jail(
                ("server",), processes=processes, supervisors=supervisors, placeholders=placeholders
            )
    
        assert isinstance(raised.value, JailSpawnFailed), repr(raised.value)
        assert supervisors.spawned == [_SUPERVISOR_PID]
>       assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
E       assert [] == [(2000, <Sign...SIGTERM: 15>)]
E         
E         Right contains one more item: (2000, <Signals.SIGTERM: 15>)
E         Use -v to get more diff

tests/integration/test_create_error_edges.py:185: AssertionError
=========================== short test summary info ============================
FAILED tests/integration/test_create_error_edges.py::test_a_state_directory_that_cannot_be_made_crosses_as_brigs_own_error
FAILED tests/integration/test_create_error_edges.py::test_an_empty_directory_that_is_not_empty_crosses_as_brigs_own_error
FAILED tests/integration/test_create_error_edges.py::test_a_supervisor_script_that_cannot_be_written_crosses_as_brigs_own_error
FAILED tests/integration/test_create_error_edges.py::test_a_teardown_that_raises_does_not_hide_the_steps_error
FAILED tests/integration/test_create_error_edges.py::test_a_close_that_raises_does_not_hide_the_steps_error
FAILED tests/integration/test_create_error_edges.py::test_a_start_that_spawned_then_failed_tears_the_spawned_supervisor_down
6 failed in 0.60s
```
<!-- SECTION:NOTES:END -->
