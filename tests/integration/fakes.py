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

from brig import ProcessUnknown, SupervisorDoneUnknown


@dataclass(frozen=True)
class _SpawnedProcess:
    """What `FakeProcesses.spawn` hands back: a fabricated process identity."""

    pid: int
    pgid: int


@dataclass
class FakeProcesses:
    """A fake of the world `brig.presentation.ports.ProcessPort` asks infra for.

    Records every call in its own state -- never touches a real process. `spawn`
    hands back a fabricated identity built from `next_pid`; `reap` and `reap_deadline`
    both report `exit_code` for whichever pid they are asked about, except
    `reap_deadline`, which reports `None` instead while `expires` is `True` -- a test's
    way to arrange a deadline-bound wait that expires rather than collecting the
    process (TASK-0001.06). `group_alive` reports `alive`, so a test can arrange a jail
    whose process already exited on its own (the walking skeleton's `true`) by leaving
    it at the default `False`, or one teardown must signal by setting it `True`.
    `group_alive_deadline` (decision-0003/TASK-0013) answers the same way as one more
    `group_alive` call -- a fake never actually polls or sleeps.

    `process_unknown`, while `True`, has `reap`, `reap_deadline` and `peek` all report
    `ProcessUnknown` instead of `exit_code` (or, for `reap_deadline`/`peek`, `None`) --
    a test's way to arrange the process being no longer this program's child to wait
    for at all (`ECHILD`: something else already released it), the race TASK-0001.06's
    review found (`reap` leaking a raw `ChildProcessError`, `reap_deadline` reporting
    it as an ordinary deadline expiry). `leader_exited`, while `True` and
    `process_unknown` is not, has `peek` report `exit_code` instead of `None` -- a
    test's way to arrange the ladder's leader having already exited and sitting as a
    deliberately held (peeked, not released) zombie throughout, which a driver then
    excludes from every `group_alive`/`group_alive_deadline` check it makes
    (decision-0003) -- a test's way to arrange a jail whose leader exits before the
    rest of its group does, TASK-0001.06's other review finding. `alive_checks` has
    `group_alive` report `True` for that many calls before falling back to `alive` --
    together with `leader_exited`, a test's way to arrange the ladder staying on
    `alive` through more `Verify` calls than a leader-only group would need, then
    finally seeing the group gone.
    """

    exit_code: int = 0
    alive: bool = False
    expires: bool = False
    process_unknown: bool = False
    leader_exited: bool = False
    alive_checks: int = 0
    next_pid: int = 1000
    spawned: list[tuple[str, ...]] = field(default_factory=list)
    spawned_inheritable_fds: list[tuple[int, ...]] = field(default_factory=list)
    reaped: list[int] = field(default_factory=list)
    reaped_deadline: list[tuple[int, float]] = field(default_factory=list)
    peek_attempts: list[int] = field(default_factory=list)
    released: list[int] = field(default_factory=list)
    signalled: list[tuple[int, signal.Signals]] = field(default_factory=list)
    checked: list[int] = field(default_factory=list)
    checked_held: list[frozenset[int]] = field(default_factory=list)
    checked_deadline: list[tuple[int, int, float]] = field(default_factory=list)

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

    def peek(self, pid: int) -> int | None | ProcessUnknown:
        """Record `pid`; report `ProcessUnknown` while `process_unknown`, `exit_code`
        while `leader_exited`, or `None` otherwise (still running).
        """
        self.peek_attempts.append(pid)
        if self.process_unknown:
            return ProcessUnknown()
        return self.exit_code if self.leader_exited else None

    def release(self, pid: int) -> None:
        """Record `pid`."""
        self.released.append(pid)

    def group_alive(self, pgid: int, held: frozenset[int] = frozenset()) -> bool:
        """Record `pgid` and `held`; report `True` for `alive_checks` calls, then
        `alive`.
        """
        self.checked.append(pgid)
        self.checked_held.append(held)
        if self.alive_checks > 0:
            self.alive_checks -= 1
            return True
        return self.alive

    def group_alive_deadline(self, pid: int, pgid: int, deadline: float) -> bool:
        """Record `(pid, pgid, deadline)`; answer the same way one more `group_alive`
        call would -- a fake never actually polls or sleeps.
        """
        self.checked_deadline.append((pid, pgid, deadline))
        held = frozenset({pid}) if self.leader_exited and not self.process_unknown else frozenset()
        return self.group_alive(pgid, held)


@dataclass(frozen=True)
class _SupervisorIdentity:
    """What `FakeSupervisors.start` hands back: a fabricated supervisor identity --
    the single process the host now tracks in place of the group `_SpawnedProcess`
    stood in for (decision-0002)."""

    pid: int
    pgid: int


@dataclass
class FakeSupervisors:
    """A fake of the world `brig.presentation.ports.SupervisorPort` asks infra for
    (TASK-0001.15 step 4): the supervised path's counterpart to `FakeProcesses`.

    Records every call in its own state -- never starts a real supervisor. `start`
    hands back a fabricated identity built from `next_pid`; `await_done` reports
    `exit_code`, `None` while `expires` is `True` (a test's way to arrange a
    deadline-bound wait that times out rather than resolving), or
    `SupervisorDoneUnknown` while `done_unknown` is `True` (a test's way to arrange
    the supervisor's report being gone for good). `fail_start`, while `True`, has
    `start` raise `OSError` after recording the call -- the fakes-only way to arrange
    `create_bwrap_jail` failing once everything before the start already happened
    (`presentation/drivers/bwrap.py`'s `run` turns it into `JailSpawnFailed`).
    """

    exit_code: int = 0
    expires: bool = False
    done_unknown: bool = False
    fail_start: bool = False
    next_pid: int = 2000
    started: list[tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = field(default_factory=list)
    awaited: list[tuple[int, float]] = field(default_factory=list)
    closed: list[int] = field(default_factory=list)

    def start(self, argv: tuple[str, ...], env: tuple[tuple[str, str], ...]) -> _SupervisorIdentity:
        """Record `(argv, env)`; raise `OSError` while `fail_start`, else hand back a
        fabricated supervisor identity.

        Raises:
            OSError: `fail_start` is set.
        """
        self.started.append((argv, env))
        if self.fail_start:
            raise OSError("fake supervisor refused to start")
        pid = self.next_pid
        self.next_pid += 1
        return _SupervisorIdentity(pid=pid, pgid=pid)

    def await_done(self, pid: int, deadline: float) -> int | None | SupervisorDoneUnknown:
        """Record `(pid, deadline)`; report `exit_code`, `None` while `expires`, or
        `SupervisorDoneUnknown` while `done_unknown`.
        """
        self.awaited.append((pid, deadline))
        if self.done_unknown:
            return SupervisorDoneUnknown()
        return None if self.expires else self.exit_code

    def close(self, pid: int) -> None:
        """Record `pid`."""
        self.closed.append(pid)


@dataclass
class FakeChannelDirectories:
    """A fake of the world `brig.presentation.ports.ChannelDirectoryPort` asks for
    (TASK-0001.25, TASK-0001.26): `allocate` hands back `path` and counts itself in
    `allocated`; `create` and `remove` record the path in `created`/`removed`.
    Bookkeeping only -- never touches the filesystem.
    """

    path: str = "/fake/state/channels/0001"
    allocated: int = 0
    created: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def allocate(self) -> str:
        """Count the call and hand back `path`."""
        self.allocated += 1
        return self.path

    def create(self, path: str) -> None:
        """Record `path`."""
        self.created.append(path)

    def remove(self, path: str) -> None:
        """Record `path`."""
        self.removed.append(path)
