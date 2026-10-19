"""Exceptions brig's public API can raise for the bwrap walking skeleton (decision-0001
rule 13).

One subclass per failure. `presentation/drivers/bwrap.py` and `presentation/api.py` (the
real wiring, by that module's own docstring) are the only modules that call infra, so
they are the only ones that catch an infra exception and raise one of these in its
place -- an embedder handles brig's own types without ever needing infra's.
"""

from brig.domain.effects import Process
from brig.domain.policy.paths import Bind


class StateDirectoryUnreachable(Exception):
    """Raised when a caller's own `FsPolicy` names a read-only ancestor bind of
    brig's own state directory whose source does not already contain that
    directory's own leaf (TASK-0001.22) -- refused here, before bwrap is ever
    invoked, in place of letting this surface as `JailExitUnknown` (then
    `JailTeardownFailed` on the following `destroy_jail`) once bwrap itself
    cannot create the mountpoint (`bwrap: Can't mkdir <state_dir>: Read-only
    file system`, measured against real bwrap).

    `presentation/api.py`'s `_check_state_dir_reachable` is the one place this
    is raised, using `domain/jail_types/bwrap.py`'s own pure
    `covering_ancestor_bind` to find the offending bind and then doing the one
    host filesystem check (I/O, rule 2) that decides whether it actually
    blocks `state_dir`.

    Args:
        state_dir: Brig's own resolved state directory (`infra/state_dir.py`)
            that the jail's policy would leave unreachable.
        ancestor: The policy's own bind whose read-only ancestor mount blocks it.
    """

    def __init__(self, state_dir: str, ancestor: Bind) -> None:
        super().__init__(
            f"policy names a read-only ancestor bind of brig's own state directory "
            f"({state_dir!r}) at {ancestor.jail_path!r} (sourced from "
            f"{ancestor.host_path!r}), which does not contain the directory's own "
            f"leaf -- make that bind writable, include the leaf in its source, or "
            f"move BRIG_HOME outside it"
        )
        self.state_dir = state_dir
        self.ancestor = ancestor


class StateDirectoryInvalid(Exception):
    """Raised when `BRIG_HOME` names a value brig's own state directory cannot
    use (`infra/state_dir.py`'s `resolve`) -- translated here from infra's own
    `ValueError`, the one place this module's driver-exception-boundary rule
    says that happens (an embedder handles brig's own types without ever
    seeing `infra`'s).

    Args:
        value: The offending `BRIG_HOME` value `resolve` refused -- not an
            absolute path.
    """

    def __init__(self, value: str) -> None:
        super().__init__(f"BRIG_HOME is not usable as brig's own state directory: {value!r}")
        self.value = value


class JailSpawnFailed(Exception):
    """Raised when a jail's one process could not be started.

    Args:
        argv: The command that could not be run as the jail's process.
    """

    def __init__(self, argv: tuple[str, ...]) -> None:
        super().__init__(f"could not spawn jail process: {argv!r}")
        self.argv = argv


class JailWaitTimedOut(Exception):
    """Raised when waiting for a jail's process to exit passed its deadline.

    Args:
        process: The jail's process, whose exit wait passed its deadline with the
            process still unreaped.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail process did not exit before its deadline: {process!r}")
        self.process = process


class JailExitUnknown(Exception):
    """Raised when a jail's process's exit code could not be collected because
    something else reaped it first.

    Args:
        process: The jail's process, no longer this program's child to wait for at
            all (`ECHILD`) by the time `run_jail` waited on it -- an embedder that
            auto-reaps its own children, or a signal disposition that discards them,
            is the usual cause. Unlike `JailWaitTimedOut`, retrying the wait can never
            succeed: the exit code is gone for good.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail process already reaped elsewhere, exit code lost: {process!r}")
        self.process = process


class JailTeardownFailed(Exception):
    """Raised when a jail's process group was still alive after the kill ladder.

    Args:
        process: The jail's process, whose group the kill ladder's last verify still
            found alive after signalling it with both TERM and KILL.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail's process group still alive after teardown: {process!r}")
        self.process = process


class ChannelNameRefused(Exception):
    """Raised by `reserve_channels` when a declared channel's name would not name
    exactly one file inside the jail's channel directory -- empty, `.` or `..`,
    containing `/` or NUL, or repeating an earlier channel's name
    (`domain/channels.py`'s `reserve`, TASK-0001.25). Nothing has been reserved or
    started when this is raised.

    Args:
        name: The refused channel name.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"channel name {name!r} would escape or repeat in the jail's channel "
            f"directory -- name each channel with one distinct path component"
        )
        self.name = name
