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

    def reap_nowait(self, pid: int) -> int | None:
        """Collect `pid`'s exit status if it has already exited, without blocking."""
        ...

    def group_alive(self, pgid: int) -> bool:
        """Report whether any process in the group `pgid` is still alive."""
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
