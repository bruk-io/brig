"""Exceptions brig's public API can raise for the bwrap walking skeleton (decision-0001
rule 13).

One subclass per failure. `presentation/drivers/bwrap.py` is the only module that calls
infra, so it is the only one that catches an infra exception and raises one of these in
its place -- an embedder handles brig's own types without ever needing infra's.
"""

from brig.domain.effects import Process


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
