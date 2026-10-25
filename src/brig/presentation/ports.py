"""Protocols the presentation layer asks infra to satisfy (decision-0001 rule 7).

A jail type's driver takes its infra calls through a port like this one, never the
concrete module by name in its own signatures; `presentation/api.py` wires the real
`brig.infra.processes` module in by default, and a test passes a fake of the same shape
instead (rule 5) -- nothing here needs to know which.

`ProcessUnknown` below mirrors `infra.processes`'s own sentinel of the same name the
way `_ProcessIdentity` mirrors `SpawnedProcess`, rather than importing it: a real
`ProcessPort` (`presentation/api.py`'s wiring) translates infra's version into this
one, so this module -- and everything that imports `ProcessUnknown` from it, down to
`brig`'s public API that `tests/integration/fakes.py` reaches it through (rule 4) --
never names infra's own type (rule 13: an embedder handles brig's types, never
infra's).
"""

import signal
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


@dataclass(frozen=True)
class ProcessUnknown:
    """The value a `ProcessPort`'s `reap` and `reap_deadline` return in place of an
    exit code when the process waited for is no longer this program's child to wait
    for at all (`ECHILD`): something else already collected it, and its exit code
    cannot be recovered now.

    See the module docstring for why this mirrors, rather than imports, infra's own
    sentinel of the same name.
    """


class _ProcessIdentity(Protocol):
    """Presentation's own shape for whatever `ProcessPort.spawn` hands back: a pid and
    the pgid of the group it leads, both read-only.

    Just the two a driver reads. Infra's `SpawnedProcess` also carries
    `session_detached`, which teardown has no use for -- it signals and probes the
    process *group*, which both of infra's spawn mechanisms give it -- so naming it here
    would oblige every rule-5 fake to carry a field nothing asks for.

    Not infra's concrete `SpawnedProcess` dataclass: a nominal return type there would
    make every rule-5 fake of this port incompatible with it at every call site, since
    a same-shaped dataclass under a different name is not a subtype of a concrete
    class. Declared as properties rather than plain attributes, because a `Protocol`
    attribute is read-write by default and every implementation of this shape -- the
    real one and every fake -- is a frozen dataclass, which is not.
    """

    @property
    def pid(self) -> int: ...

    @property
    def pgid(self) -> int: ...


class ProcessPort(Protocol):
    """What a jail type's driver needs from infra to run its one process.

    Matches `brig.infra.processes`'s own functions one for one in shape, though not
    quite verbatim: `presentation/api.py`'s default wiring wraps `reap` and
    `reap_deadline` just enough to translate infra's own `ProcessUnknown` into this
    module's, so no infra type ever reaches a driver through this port.
    """

    def spawn(self, argv: tuple[str, ...], inheritable_fds: tuple[int, ...]) -> _ProcessIdentity:
        """Start `argv` as a new process, the leader of a process group of its own.

        `inheritable_fds` is the jail type's complete allow-list (TASK-0001.05 AC#1):
        every other fd this process has open and inheritable is closed in the new one
        before it runs.
        """
        ...

    def reap(self, pid: int) -> int | ProcessUnknown:
        """Wait for `pid` to exit, and return its exit code.

        Returns `ProcessUnknown` instead if `pid` is no longer this process's child
        to wait for at all (`ECHILD`): something else already collected it.
        """
        ...

    def reap_deadline(self, pid: int, deadline: float) -> int | None | ProcessUnknown:
        """Wait for `pid` to exit, giving up and returning `None` once `deadline`
        passes.

        Returns `ProcessUnknown` instead -- never `None` -- if `pid` is no longer
        this process's child to wait for at all (`ECHILD`): something else already
        collected it, so no later wait will ever succeed either.
        """
        ...

    def signal_group(self, pgid: int, sig: signal.Signals) -> None:
        """Send `sig` to every process in the group `pgid`."""
        ...

    def peek(self, pid: int) -> int | None | ProcessUnknown:
        """Observe whether `pid` has exited, without releasing its pid for reuse
        (decision-0003).

        Returns the exit code if `pid` has already exited; `None` if still
        running; `ProcessUnknown` instead if `pid` is no longer this process's
        child to wait for at all (`ECHILD`): something already released it.
        """
        ...

    def release(self, pid: int) -> None:
        """Release `pid`'s exit status for real, once nothing will ever peek or
        wait on it again.

        A no-op where `pid` has not exited yet, or is no longer this process's
        child to wait for at all: there is nothing left to release either way.
        """
        ...

    def group_alive(self, pgid: int, held: frozenset[int]) -> bool:
        """Report whether anything in the group `pgid`, other than a pid named in
        `held`, is still alive.

        `held` names a pid a caller already knows has exited and is being
        deliberately kept unreleased (`peek`, above) -- it must not itself read
        as "this group is still alive" (decision-0003). No default here (unlike
        `infra.processes.group_alive`'s own): a driver always computes and passes
        `held` explicitly, and a `Callable`-typed field (`_RealProcesses`, in
        `presentation/api.py`) cannot express an optional parameter a Protocol
        method can.
        """
        ...

    def group_alive_deadline(self, pid: int, pgid: int, deadline: float) -> bool:
        """Poll `group_alive` for the group `pgid`, excluding `pid` once it has
        exited, until it reports gone or `time.monotonic()` passes `deadline`
        (the kill ladder's post-KILL grace window, TASK-0001.07).

        Returns `False` as soon as the group reads gone; `True` once `deadline`
        passes with something still alive.
        """
        ...


@dataclass(frozen=True)
class SupervisorDoneUnknown:
    """The value a `SupervisorPort`'s `await_done` returns in place of an exit code
    when the supervisor's report for this process can never be recovered now: the
    events pipe closed with no `done` event ever having arrived, or reading or
    decoding it failed outright. Mirrors `infra.supervisor.link`'s own sentinel of
    the same name the way `ProcessUnknown` above already mirrors
    `infra.processes`'s (this module's own docstring), rather than importing it; a
    real `SupervisorPort` (`presentation/api.py`'s wiring) translates infra's
    version into this one.

    Distinct from `None`, which `await_done` returns instead when `deadline` passes
    first with the supervisor simply not done yet: a later `await_done` call can
    still succeed there, unlike this one.
    """


class SupervisorPort(Protocol):
    """What a jail type's driver needs from infra to start and wait on the
    supervised path's one process: the jail's supervisor itself, in place of
    `ProcessPort` for the normal create/run journey (decision-0002). Matches
    `infra.supervisor.link.LiveSupervisors`'s own shape, though not quite
    verbatim, for the same reason `ProcessPort`'s own docstring gives.
    """

    def start(self, argv: tuple[str, ...], env: tuple[tuple[str, str], ...]) -> _ProcessIdentity:
        """Start the jail's supervisor -- however this port's own implementation
        launches it -- with `argv`/`env` as the one command it runs as its own
        child, and return the supervisor's own process identity: the single
        process the host now tracks in place of the group a direct `Spawn` of the
        real command would have left it tracking.
        """
        ...

    def await_done(self, pid: int, deadline: float) -> int | None | SupervisorDoneUnknown:
        """Wait for the supervisor identified by `pid` (`start`'s own identity) to
        report its one supervised command done, giving up once `deadline` passes.

        Returns the supervised command's exit code once the supervisor reports it
        done; `None` if `deadline` arrives first with it not yet done -- a later
        `await_done` call can still succeed; `SupervisorDoneUnknown` instead if
        that can never be recovered now.
        """
        ...

    def close(self, pid: int) -> None:
        """Release whatever this port is still holding open for the supervisor
        identified by `pid`, once nothing will ask about it again.

        A no-op where nothing is held open for `pid` any more -- `await_done`
        already released it on a terminal outcome, or nothing was ever started for
        it. Call this one regardless from teardown, for the jail destroyed before
        anything ever awaited it.
        """
        ...


class ChannelReadinessRefusal(Enum):
    """Why a `ChannelReadinessPort` refused a connection that did connect
    (decision-0005 items 2, 5 and 6, TASK-0001.27 AC#1).

    A closed set of three names, mirroring the three reasons
    `infra.sockets.channel_ready` can refuse for -- `presentation/api.py`'s default
    wiring translates infra's own string constants into these, the same way its
    `_reap` translates infra's `ProcessUnknown`. An embedder matches on these;
    nothing under `infra/` is named here (rule 13).
    """

    PEER_OUTSIDE_JAIL = "peer_outside_jail"
    """The peer connected, and its PID namespace is not the jail's own -- a listener
    in a namespace strictly *nested* under the jail's is refused too, strict
    equality only, no `NS_GET_PARENT` walk (decision-0005 item 2).
    """

    PEER_LOOKUP_FAILED = "peer_lookup_failed"
    """The peer connected, but its identity could not be established: any `OSError`
    from `SO_PEERPIDFD`, the `ns/pid` readlink or the pidfd re-check (`EINVAL` from
    a reaped peer, `EACCES` from a different-uid peer, `ESRCH`, anything else), and
    the pid-mismatch case where the two reads disagree (decision-0005 item 5).
    """

    KERNEL_UNSUPPORTED = "kernel_unsupported"
    """This kernel cannot identify a connected peer at all: no `SO_PEERPIDFD`
    (Linux before 6.5). Readiness fails closed with this rather than falling back to
    the bare `SO_PEERCRED` pid, which is not re-checkable and so reopens the
    pid-reuse window (decision-0005 item 6).
    """


@dataclass(frozen=True)
class ChannelReady:
    """A channel is ready: this connect reached a socket whose listening process is
    inside the jail's own PID namespace.

    What that proves, exactly, and nothing more: a process in that namespace called
    `listen()` on the socket that answered -- not that it is the process accepting,
    not that it is still alive, not that it is the process the embedder meant
    (decision-0005 item 4).
    """


@dataclass(frozen=True)
class ChannelNotReady:
    """Nothing is listening at the channel's path yet: the connect itself failed, so
    no peer was reached to say anything about.

    Distinct from `ChannelRefused`, and the difference is what a caller must act on:
    this is a transient state, worth polling through until a deadline, while a
    refusal is a terminal answer about this connection (decision-0005 item 1: a
    consumer that reconnects must verify again).
    """


@dataclass(frozen=True)
class ChannelRefused:
    """A connection reached a peer, and readiness refused it: `reason` says why
    (`ChannelReadinessRefusal`).

    Returned, never raised (decision-0005 item 5) -- a refusal is an ordinary answer
    to "is this channel ready", not an exceptional situation, and `await_channel_ready`
    treats it as terminal for the connection it describes.
    """

    reason: ChannelReadinessRefusal


class ChannelReadinessPort(Protocol):
    """What a jail type's driver needs from infra to answer "is this channel ready",
    verified rather than by path existence (decision-0002 item 2, decision-0005).

    Matches `brig.infra.sockets.channel_ready`'s own shape one for one, the same way
    `ProcessPort` mirrors `brig.infra.processes`: `presentation/api.py`'s default
    wiring translates infra's own `ChannelRefusalReason` strings and its `ChannelReady`/
    `ChannelNotReady` sentinels into this module's values, so no infra type crosses
    this port.

    Finding the jail's own PID namespace (`infra.sockets.jail_pid1_namespace`) is
    deliberately **not** behind a port: it is jail setup, called once from
    `create_bwrap_jail` directly, the same way `_check_state_dir_reachable` calls
    `bwrap.covering_ancestor_bind` directly. Nothing needs to fake "which pid is
    bwrap's child"; a test needs to fake "is this channel ready yet", which is this
    port.
    """

    def ready(
        self, path: str, jail_namespace_fd: int
    ) -> ChannelReady | ChannelNotReady | ChannelRefused:
        """Connect to `path` once, and report whether the process that called
        `listen()` on the socket that answered is inside the jail's PID namespace --
        the one `jail_namespace_fd`, an open fd on it, names.

        `jail_namespace_fd` is the caller's own precondition (it comes from
        `create_bwrap_jail`, and is closed exactly once, by `destroy_jail`): passing
        one that is not open raises `OSError`. Every other outcome is one of the
        three returned values, never a raise.
        """
        ...


class ChannelDirectoryPort(Protocol):
    """Where a jail's per-jail channel directory goes (TASK-0001.25), and its
    lifecycle on the world `create_bwrap_jail`/`destroy_jail` actually run against
    (TASK-0001.26).

    `presentation/api.py`'s default names a fresh path under brig's own state
    directory (`allocate`) and creates/removes it for real through `infra/sockets.py`;
    a fake records all three calls instead of touching anything.
    """

    def allocate(self) -> str:
        """Name a new per-jail channel directory's host path, distinct from every
        other jail's.

        Names only -- creates nothing (`reserve_channels`'s own docstring: a refused
        channel name must never have created anything to clean up).
        """
        ...

    def create(self, path: str) -> None:
        """Make `path` exist, private to the owning user, and every missing parent
        of it -- idempotent, a no-op where it already exists.
        """
        ...

    def remove(self, path: str) -> None:
        """Remove `path` and everything written inside it.

        Raises `OSError` (`FileNotFoundError` where `path` is already gone) rather
        than swallowing it: the caller decides, the same split as the supervisor
        script's own `unlink` -- `destroy_jail` and `create_bwrap_jail`'s cleanup
        swallow it, since an already-gone channel directory is fine there.
        """
        ...
