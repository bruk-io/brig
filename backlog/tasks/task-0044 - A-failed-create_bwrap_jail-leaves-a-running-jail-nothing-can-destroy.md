---
id: TASK-0044
title: A failed create_bwrap_jail leaves a running jail nothing can destroy
status: In Progress
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:37:00Z'
labels:
  - brig
  - lifecycle
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (reasoned from code): in presentation/drivers/bwrap.py, once run(operations.create...) started the supervisor, _placeholders.attach or _namespace_fd_for can still raise (ChannelNamespaceNotFound is documented 'with process still running'). The except path unlinks the script, removes the channel directory and releases placeholders while the jail still mounts over them, and never tears the process down; the embedder gets no Jail to destroy. Proposed: once a process exists, the failure path runs operations.destroy and releases placeholders only on GONE; share one cleanup with destroy_jail.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Once the supervisor process exists, every failure inside create_bwrap_jail tears the jail down through the same destroy path destroy_jail uses, and releases placeholders only once teardown reports the process gone
- [ ] #2 An integration test with fakes fails each step after the start (placeholder attach, the namespace scan) and asserts the process was destroyed and nothing was released while it lived; recorded failing before the fix
- [ ] #3 create_bwrap_jail and destroy_jail share one cleanup function, so the two paths cannot disagree again
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-03: criteria written in a separate edit right after promotion (finish-moved for that reason only).

Repro at 228b2980782d, test files: tests/integration/test_create_failure_tears_down.py; command: `uv run pytest tests/integration/test_create_failure_tears_down.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
________ test_a_failed_namespace_scan_tears_the_started_supervisor_down ________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-520/test_a_failed_namespace_scan_t0')

    def test_a_failed_namespace_scan_tears_the_started_supervisor_down(tmp_path: Path) -> None:
        """The scan finds no PID 1 under a running supervisor: `ChannelNamespaceNotFound` still
        propagates, and before it does the supervisor's group was verified, sent TERM, verified
        gone and its pid released, and its events pipe closed."""
        proc_root = str(tmp_path / "proc")
        plant_fake_proc(proc_root, {_SUPERVISOR_PID: (1, str(_SUPERVISOR_PID))})
        directories = FakeChannelDirectories()
        processes = FakeProcesses(alive_checks=1)
        supervisors = FakeSupervisors()
        reserved = reserve_channels((Channel("ctl"),), directories=directories)
    
        with pytest.raises(ChannelNamespaceNotFound):
            create_bwrap_jail(
                ("server",),
                channels=reserved,
                processes=processes,
                supervisors=supervisors,
                directories=directories,
                proc_root=proc_root,
            )
    
>       assert processes.signalled == [(_SUPERVISOR_PID, signal.SIGTERM)]
E       assert [] == [(2000, <Sign...SIGTERM: 15>)]
E         
E         Right contains one more item: (2000, <Signals.SIGTERM: 15>)
E         Use -v to get more diff

tests/integration/test_create_failure_tears_down.py:51: AssertionError
=========================== short test summary info ============================
FAILED tests/integration/test_create_failure_tears_down.py::test_a_failed_namespace_scan_tears_the_started_supervisor_down
1 failed in 5.11s
```
<!-- SECTION:NOTES:END -->
