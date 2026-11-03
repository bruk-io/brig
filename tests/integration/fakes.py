"""Fakes of the world at infra's edge, for brig's integration suite: doubles live only here, and
a test asserts on their state, never a patch (decision-0001 rule 5). They import only brig's
public API (rule 4), so each satisfies its port structurally.
"""

import os
import signal
import socket
from dataclasses import dataclass, field

from brig import (
    ChannelNotReady,
    ChannelReady,
    ChannelRefused,
    ExitCodeUnknown,
)


@dataclass
class FakeProcesses:
    """A fake `ProcessPort` that records every call and touches no process.

    `group_alive` reports `alive`, after `True` for the first `alive_checks` calls; the default
    `False` is a jail whose command already exited. `peek` reports `exit_code` while
    `leader_exited` (a held, exited leader the driver leaves out of each check), `None`
    otherwise, and `ExitCodeUnknown` while `process_unknown` (no longer a child, `ECHILD`).
    `group_alive_deadline` answers as one more `group_alive` call, without polling.
    """

    exit_code: int = 0
    alive: bool = False
    process_unknown: bool = False
    leader_exited: bool = False
    alive_checks: int = 0
    peek_attempts: list[int] = field(default_factory=list)
    released: list[int] = field(default_factory=list)
    signalled: list[tuple[int, signal.Signals]] = field(default_factory=list)
    checked: list[int] = field(default_factory=list)
    checked_held: list[frozenset[int]] = field(default_factory=list)
    checked_deadline: list[tuple[int, int, float]] = field(default_factory=list)

    def signal_group(self, pgid: int, sig: signal.Signals) -> None:
        """Record the signal sent to `pgid`."""
        self.signalled.append((pgid, sig))

    def peek(self, pid: int) -> int | None | ExitCodeUnknown:
        """Record `pid`; report `ExitCodeUnknown` while `process_unknown`, `exit_code`
        while `leader_exited`, or `None` otherwise (still running).
        """
        self.peek_attempts.append(pid)
        if self.process_unknown:
            return ExitCodeUnknown()
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
    """What `FakeSupervisors.start` hands back: a fabricated supervisor identity."""

    pid: int
    pgid: int


@dataclass
class FakeSupervisors:
    """A fake `SupervisorPort` that records every call and starts nothing.

    `start` hands back an identity from `next_pid`, or raises `OSError` while `fail_start`
    (which the driver turns into `JailSpawnFailed`). `await_done` reports `exit_code`, `None`
    while `expires` (a wait that timed out), or `ExitCodeUnknown` while `done_unknown`.
    """

    exit_code: int = 0
    expires: bool = False
    done_unknown: bool = False
    fail_start: bool = False
    next_pid: int = 2000
    started: list[tuple[tuple[str, ...], frozendict[str, str]]] = field(default_factory=list)
    awaited: list[tuple[int, float]] = field(default_factory=list)
    closed: list[int] = field(default_factory=list)

    def start(self, argv: tuple[str, ...], env: frozendict[str, str]) -> _SupervisorIdentity:
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

    def await_done(self, pid: int, deadline: float) -> int | None | ExitCodeUnknown:
        """Record `(pid, deadline)`; report `exit_code`, `None` while `expires`, or
        `ExitCodeUnknown` while `done_unknown`.
        """
        self.awaited.append((pid, deadline))
        if self.done_unknown:
            return ExitCodeUnknown()
        return None if self.expires else self.exit_code

    def close(self, pid: int) -> None:
        """Record `pid`."""
        self.closed.append(pid)


@dataclass
class FakeChannelDirectories:
    """A fake `ChannelDirectoryPort`: `allocate` hands back `path` and counts itself; `create`
    and `remove` record the path; while `fail_create`, `create` raises `OSError` and records
    nothing. Touches no filesystem.
    """

    path: str = "/fake/state/channels/0001"
    fail_create: bool = False
    allocated: int = 0
    created: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def allocate(self) -> str:
        """Count the call and hand back `path`."""
        self.allocated += 1
        return self.path

    def create(self, path: str) -> None:
        """Record `path`; raise `OSError` while `fail_create`, recording nothing.

        Raises:
            OSError: `fail_create` is set.
        """
        if self.fail_create:
            raise OSError(28, "fake host: no space left on device")
        self.created.append(path)

    def remove(self, path: str) -> None:
        """Record `path`."""
        self.removed.append(path)


@dataclass
class FakePlaceholders:
    """A fake `PlaceholderPort`, for a host where brig held placeholders for a jail: `hold`
    records the paths it was given and hands back `record` whatever they are (a jail started
    with a caller's own `supervisors` compiles no policy, so it is given none); `attach`
    records `(record, pid)`, raising `OSError` while `fail_attach`; `release` records the
    record. Touches no filesystem.
    """

    record: str = "fake-placeholders-0001"
    fail_attach: bool = False
    held: list[tuple[str, ...]] = field(default_factory=list)
    attached: list[tuple[str, int]] = field(default_factory=list)
    released: list[str] = field(default_factory=list)

    def hold(self, paths: tuple[str, ...]) -> str:
        """Record `paths` and hand back `record`."""
        self.held.append(paths)
        return self.record

    def attach(self, record: str, pid: int) -> None:
        """Record `(record, pid)`; raise `OSError` while `fail_attach`.

        Raises:
            OSError: `fail_attach` is set.
        """
        self.attached.append((record, pid))
        if self.fail_attach:
            raise OSError(28, "fake host: no space left on device")

    def release(self, record: str) -> None:
        """Record `record`."""
        self.released.append(record)


@dataclass
class FakeChannelReadiness:
    """A fake `ChannelReadinessPort`: `ready` records what it was asked and answers with the
    next of `outcomes`, repeating the last once they run out. No `/proc`, clock or path.

    `ChannelReady` in the script (the class, not an instance) is an attempt that connects: the
    fake makes a socket pair, hands one end out in a `ChannelReady` for the caller to own, and
    keeps the other in `peers`, so a test can show the connection the caller got is the one the
    fake made and is still open. `close` closes the peers.
    """

    outcomes: list[type[ChannelReady] | ChannelNotReady | ChannelRefused] = field(
        default_factory=lambda: [ChannelReady]
    )
    asked: list[tuple[str, int]] = field(default_factory=list)
    handed_out: list[socket.socket] = field(default_factory=list)
    peers: list[socket.socket] = field(default_factory=list)

    def ready(
        self, path: str, jail_namespace_fd: int
    ) -> ChannelReady | ChannelNotReady | ChannelRefused:
        """Record `(path, jail_namespace_fd)`; answer with the next scripted outcome,
        repeating the last one once the script is exhausted, and a fresh connection for each
        ready one.
        """
        self.asked.append((path, jail_namespace_fd))
        index = min(len(self.asked), len(self.outcomes)) - 1
        outcome = self.outcomes[index]
        if outcome is ChannelReady:
            ours, theirs = socket.socketpair()
            self.handed_out.append(ours)
            self.peers.append(theirs)
            return ChannelReady(ours)
        assert not isinstance(outcome, type)
        return outcome

    def close(self) -> None:
        """Close every peer end the fake kept."""
        for peer in self.peers:
            peer.close()


def plant_fake_proc(
    root: str, entries: dict[int, tuple[int, str]], zombies: frozenset[int] = frozenset()
) -> None:
    """Build a procfs-shaped tree under the real directory `root`, one entry per
    `pid: (ppid, nspid)`, for a `/proc` scan to read with real I/O: a `status` with `State:`
    (zombie for each of `zombies`), `PPid:` and `NSpid:`, and an empty `ns/pid` to open.
    """
    os.makedirs(root, exist_ok=True)
    for pid, (ppid, nspid) in entries.items():
        state = "Z (zombie)" if pid in zombies else "S (sleeping)"
        entry = os.path.join(root, str(pid))
        os.makedirs(os.path.join(entry, "ns"), exist_ok=True)
        with open(os.path.join(entry, "status"), "w") as handle:
            handle.write(
                f"Name:\tfake\nState:\t{state}\nPid:\t{pid}\nPPid:\t{ppid}\nNSpid:\t{nspid}\n"
            )
        with open(os.path.join(entry, "ns", "pid"), "w") as handle:
            handle.write("")
