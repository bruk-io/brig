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
