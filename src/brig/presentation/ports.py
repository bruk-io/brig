"""The Protocols a driver calls infra through (decision-0001 rule 7), and the readiness outcomes
an embedder matches on. `presentation/jail.py` wires the real infra in; a test passes a fake of
the same shape (rule 5). No infra type crosses a port: the real wiring translates infra's
sentinels into domain's or this module's values.
"""

import signal
import socket
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from brig.domain.effects import ExitCodeUnknown, ExitOutcome
from brig.domain.policy.egress import Destination, EgressChangeKind
from brig.domain.policy.egress_record import EgressDecision, EgressRecord


class _ProcessIdentity(Protocol):
    """A started process's pid and the pgid of the group it leads, read-only. A Protocol, not
    infra's spawned-process record, so a fake's own frozen dataclass satisfies it."""

    @property
    def pid(self) -> int: ...

    @property
    def pgid(self) -> int: ...


class ProcessPort(Protocol):
    """What a driver needs from infra to signal, check and release a jail's process group."""

    def signal_group(self, pgid: int, sig: signal.Signals) -> None:
        """Send `sig` to every process in the group `pgid`; a no-op once it is gone."""
        ...

    def peek(self, pid: int) -> int | None | ExitCodeUnknown:
        """Whether `pid` has exited, without releasing it (decision-0003): its exit code,
        `None` while it runs, or `ExitCodeUnknown` once it is no longer this process's child
        (`ECHILD`)."""
        ...

    def release(self, pid: int) -> None:
        """Release `pid` for reuse; a no-op if it has not exited or is no longer a child."""
        ...

    def group_alive(self, pgid: int, held: frozenset[int]) -> bool:
        """Whether anything in the group `pgid` other than the pids in `held` (exited, peeked
        and deliberately unreleased) is still alive."""
        ...

    def group_alive_deadline(self, pid: int, pgid: int, deadline: float) -> bool:
        """Poll `group_alive` for `pgid`, leaving `pid` out once it has exited, until it reads
        gone (`False`) or `time.monotonic()` passes `deadline` (`True`)."""
        ...


class SupervisorPort(Protocol):
    """What a driver needs from infra to start a jail's supervisor and wait on it
    (decision-0002)."""

    def start(self, argv: tuple[str, ...], env: frozendict[str, str]) -> _ProcessIdentity:
        """Start the jail's supervisor with `argv` in `env` as its one command, and return the
        supervisor's identity: the one process the host tracks.

        Raises:
            OSError: the supervisor could not be started, and nothing was spawned.
            JailSpawnFailed: the supervisor was spawned and a later step of the start failed;
                its `process` is the spawned supervisor, which the caller tears down
                (TASK-0046).
        """
        ...

    def await_done(self, pid: int, deadline: float) -> ExitOutcome:
        """Wait, until `deadline`, for the supervisor `pid` to report its command done: the exit
        code, `None` if the deadline passed first (a later call may still succeed), or
        `ExitCodeUnknown` if the report can never be recovered."""
        ...

    def close(self, pid: int) -> None:
        """Release what is held open for the supervisor `pid`; a no-op if nothing is."""
        ...


class PlaceholderPort(Protocol):
    """What a driver needs from infra to hold the directories a jail mounts over at absent
    paths, tie them to the jail's process, and release them once no jail mounts over them
    (TASK-0027). A record is the port's own name for one jail's hold."""

    def hold(self, paths: tuple[str, ...]) -> str | None:
        """Make the directories missing on the way to each of `paths` and record them as one
        jail's, and return the record, or `None` when there is nothing to record. An `OSError`
        propagates, whatever was made removed again first."""
        ...

    def attach(self, record: str, pid: int) -> None:
        """Note that the jail holding `record` is the process `pid`, which from now on says
        whether the jail is alive. An `OSError` propagates."""
        ...

    def release(self, record: str) -> None:
        """Remove `record` and the directories no live jail still mounts over. An `OSError`
        propagates for the caller to judge."""
        ...


class MembersPort(Protocol):
    """What a Seatbelt jail's teardown needs from infra on Darwin: to find and kill every process
    that carries the jail's profile, however it left the jail's process group (decision-0010
    item 2)."""

    def kill(self, mark: str, decoy: str, deadline: float) -> bool:
        """Kill every process whose sandbox allows `mark` and refuses `decoy`, looking again
        until none is left (`True`) or `time.monotonic()` passes `deadline` (`False`)."""
        ...


class ChannelReadinessRefusal(Enum):
    """Why readiness refused a connection that did connect (decision-0005)."""

    PEER_OUTSIDE_JAIL = "peer_outside_jail"
    """The listener's PID namespace is not the jail's own; a nested one is refused too
    (strict equality, decision-0005 item 2). A symbolic link at the channel's name is refused
    so too, before any connect: what it names can be any socket the embedder can reach
    (TASK-0045)."""

    PEER_LOOKUP_FAILED = "peer_lookup_failed"
    """The listener could not be identified: an `OSError` reading its pidfd or namespace, or
    the pid and the pidfd disagreeing (decision-0005 item 5)."""

    KERNEL_UNSUPPORTED = "kernel_unsupported"
    """The kernel has no `SO_PEERPIDFD` (Linux before 6.5); readiness does not fall back to
    `SO_PEERCRED`, whose pid can be reused (decision-0005 item 6)."""


@dataclass(frozen=True)
class ChannelReady:
    """The connect reached a socket on which a process inside the jail's PID namespace called
    `listen()`, and nothing more: not that it accepts, is alive, or is the one meant
    (decision-0005 item 4).

    `connection` is that connect, still open, and the only connection readiness vouches for.
    The embedder speaks the channel's protocol over it, owns it and closes it (`with
    ready.connection:`), and never dials the reservation's `bound_path` itself: the jail can
    write its channel directory, so once readiness has passed it can put a symbolic link to any
    host socket there, and a plain connect follows it (TASK-0001.34). A second connection needs
    a second `await_channel_ready`. The socket is blocking, with no timeout, and is not
    inherited by a process spawned later."""

    connection: socket.socket


@dataclass(frozen=True)
class ChannelNotReady:
    """Nothing at the channel's name takes a connection yet (no socket there, or a listener
    whose backlog is full): transient, worth polling."""


@dataclass(frozen=True)
class ChannelJailFinished:
    """The jail's command had finished, and taken its namespace with it, before
    `create_bwrap_jail` looked for it: nothing will ever listen. Terminal. What it wrote to
    the channel directory stays until `destroy_jail`."""


@dataclass(frozen=True)
class ChannelRefused:
    """Readiness refused this connection for `reason`. Terminal for this connection; one that
    reconnects must be verified again (decision-0005 item 1)."""

    reason: ChannelReadinessRefusal


class ChannelReadinessPort(Protocol):
    """What a driver needs from infra to verify a channel is ready (decision-0005)."""

    def ready(
        self, directory_fd: int, name: str, jail_namespace_fd: int
    ) -> ChannelReady | ChannelNotReady | ChannelRefused:
        """Open `name` beneath the channel directory `directory_fd` holds, through no link,
        connect once to the socket it is, without blocking, and verify the listener is in the
        PID namespace `jail_namespace_fd` names. A link there is refused without a connect
        (TASK-0045). `ChannelReady` carries that connection, open, for the caller to own; every
        other outcome has closed it. Every outcome is returned; only a `jail_namespace_fd` that
        is not open raises `OSError`, its connection closed too."""
        ...


class ChannelDirectoryPort(Protocol):
    """Where a jail's channel directory goes, and its creation and removal."""

    def allocate(self) -> str:
        """Name a new channel directory's host path, distinct from every other jail's; creates
        nothing."""
        ...

    def create(self, path: str) -> None:
        """Make `path` and its missing parents, private to the owning user; idempotent."""
        ...

    def remove(self, path: str) -> None:
        """Remove `path` and everything in it; an `OSError` (`FileNotFoundError` once it is
        gone) propagates for the caller to judge."""
        ...


class EgressPort(Protocol):
    """What the API needs from infra to change a running jail's egress grants and to read back
    what its proxy did (decision-0009 items 5 and 6). A jail with an egress policy holds one;
    a test passes a fake of the same shape on a `Jail` it builds."""

    def change(self, kind: EgressChangeKind, destination: Destination) -> None:
        """Send the proxy one change to its grants, and record it. It applies to the next
        connection the proxy takes; one already open is left alone.

        Raises:
            JailEgressEnded: the proxy has ended (the command finished, or the jail was
                destroyed), or died; nothing was recorded.
        """
        ...

    def record(self) -> EgressRecord:
        """The grants as created and every change sent since, in order."""
        ...

    def decisions(self) -> tuple[EgressDecision, ...]:
        """The decisions the proxy made since the last call, oldest first, each returned once;
        at most a bounded number are kept between calls, and `EgressDecision.seq` shows a gap
        where some were dropped. Never blocks."""
        ...
