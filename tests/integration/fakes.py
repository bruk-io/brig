"""Fakes of the world at infra's edge, for brig's integration suite.

Doubles live only here: a fake, asserted on through its state, never a patch.

A fake here never imports past brig's public API (decision-0001 rule 4), so it
cannot name `brig.presentation.ports.ProcessPort` or `brig.infra.processes.SpawnedProcess`
directly; `_SpawnedProcess` below is this module's own record of the two fields that port
asks for. Only those two: infra's `SpawnedProcess` also carries `session_detached`, which
a driver never reads -- teardown signals and probes the process *group* -- so
`_ProcessIdentity` does not require it and this fake does not fabricate it.
`ports.py`'s `ProcessPort.spawn` returns `_ProcessIdentity`, a `Protocol` presentation
owns rather than infra's concrete dataclass, so this fake's own same-shaped
`_SpawnedProcess` satisfies it structurally without ever importing it.
"""

import signal
from dataclasses import dataclass, field

from brig import ProcessUnknown


@dataclass(frozen=True)
class _SpawnedProcess:
    """What `FakeProcesses.spawn` hands back: a fabricated process identity."""

    pid: int
    pgid: int


@dataclass
class FakeProcesses:
    """A fake of the world `brig.presentation.ports.ProcessPort` asks infra for.

    Records every call in its own state -- never touches a real process. `spawn`
    hands back a fabricated identity built from `next_pid`; `reap`, `reap_deadline` and
    `reap_nowait` all report `exit_code` for whichever pid they are asked about, except
    `reap_deadline`, which reports `None` instead while `expires` is `True` -- a test's
    way to arrange a deadline-bound wait that expires rather than collecting the
    process (TASK-0001.06). `group_alive` reports `alive`, so a test can arrange a jail
    whose process already exited on its own (the walking skeleton's `true`) by leaving
    it at the default `False`, or one teardown must signal by setting it `True`.

    `process_unknown`, while `True`, has `reap` and `reap_deadline` both report
    `ProcessUnknown` instead of `exit_code` (or, for `reap_deadline`, `None`) -- a
    test's way to arrange the process being no longer this program's child to wait
    for at all (`ECHILD`: something else already collected it), the race TASK-0001.06's
    review found (`reap` leaking a raw `ChildProcessError`, `reap_deadline` reporting
    it as an ordinary deadline expiry). `alive_checks` has `group_alive` report `True`
    for that many calls before falling back to `alive` -- a test's way to arrange a
    jail whose leader exits (and is collected) before the rest of its group does, the
    same review's other finding: the ladder stays on `alive` through more `Verify`
    calls than a leader-only group would need, then finally sees the group gone.
    """

    exit_code: int = 0
    alive: bool = False
    expires: bool = False
    process_unknown: bool = False
    alive_checks: int = 0
    next_pid: int = 1000
    spawned: list[tuple[str, ...]] = field(default_factory=list)
    spawned_inheritable_fds: list[tuple[int, ...]] = field(default_factory=list)
    reaped: list[int] = field(default_factory=list)
    reaped_deadline: list[tuple[int, float]] = field(default_factory=list)
    reap_nowait_attempts: list[int] = field(default_factory=list)
    signalled: list[tuple[int, signal.Signals]] = field(default_factory=list)
    checked: list[int] = field(default_factory=list)

    def spawn(self, argv: tuple[str, ...], inheritable_fds: tuple[int, ...]) -> _SpawnedProcess:
        """Record `argv` and hand back a fabricated process identity.

        `inheritable_fds` is recorded too (`spawned_inheritable_fds`), paired by
        position with `spawned`: this fake stands in for the world, not the fd-closing
        policy itself (that is infra's own e2e battery's job), but a test wiring a real
        jail type through still has somewhere to see what allow-list reached the edge.
        """
        self.spawned.append(argv)
        self.spawned_inheritable_fds.append(inheritable_fds)
        pid = self.next_pid
        self.next_pid += 1
        return _SpawnedProcess(pid=pid, pgid=pid)

    def reap(self, pid: int) -> int | ProcessUnknown:
        """Record `pid`; report `exit_code`, or `ProcessUnknown` while `process_unknown`."""
        self.reaped.append(pid)
        return ProcessUnknown() if self.process_unknown else self.exit_code

    def reap_deadline(self, pid: int, deadline: float) -> int | None | ProcessUnknown:
        """Record `(pid, deadline)`; report `exit_code`, `None` while `expires`, or
        `ProcessUnknown` while `process_unknown` (checked first: a process that is no
        longer this program's child to wait for at all is not merely a deadline that
        passed).
        """
        self.reaped_deadline.append((pid, deadline))
        if self.process_unknown:
            return ProcessUnknown()
        return None if self.expires else self.exit_code

    def signal_group(self, pgid: int, sig: signal.Signals) -> None:
        """Record the signal sent to `pgid`."""
        self.signalled.append((pgid, sig))

    def reap_nowait(self, pid: int) -> int | None:
        """Record `pid`; report `exit_code` collected, or `None` while still `alive`."""
        self.reap_nowait_attempts.append(pid)
        return None if self.alive else self.exit_code

    def group_alive(self, pgid: int) -> bool:
        """Record `pgid`; report `True` for `alive_checks` calls, then `alive`."""
        self.checked.append(pgid)
        if self.alive_checks > 0:
            self.alive_checks -= 1
            return True
        return self.alive
