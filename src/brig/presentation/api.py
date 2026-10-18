"""brig's public entry point (decision-0001): create a bwrap jail, run a command in it,
and destroy it, wiring `domain/operations.py` through `presentation/drivers/bwrap.py`.

The only module that names `brig.infra.processes`'s own functions, so it can bind them
into the port's default implementation; a caller wanting a fake passes its own
`processes` instead.
"""

import signal
import time
from collections.abc import Callable
from dataclasses import dataclass

from brig.domain import operations
from brig.domain.effects import ExitCodeUnknown, GroupState, Process
from brig.domain.jail_types import bwrap
from brig.infra.processes import ProcessUnknown as _InfraProcessUnknown
from brig.infra.processes import SpawnedProcess
from brig.infra.processes import group_alive as _group_alive
from brig.infra.processes import reap as _infra_reap
from brig.infra.processes import reap_deadline as _infra_reap_deadline
from brig.infra.processes import reap_nowait as _reap_nowait
from brig.infra.processes import signal_group as _signal_group
from brig.infra.processes import spawn as _spawn
from brig.presentation.drivers.bwrap import run
from brig.presentation.errors import JailExitUnknown, JailTeardownFailed, JailWaitTimedOut
from brig.presentation.ports import ProcessPort, ProcessUnknown


def _reap(pid: int) -> int | ProcessUnknown:
    """Adapt infra's `reap` to `ProcessPort`'s contract: translate infra's own
    `ProcessUnknown` sentinel into this port's, the one place the real wiring knows
    both (rule 13: no infra type crosses this port).
    """
    result = _infra_reap(pid)
    return ProcessUnknown() if isinstance(result, _InfraProcessUnknown) else result


def _reap_deadline(pid: int, deadline: float) -> int | None | ProcessUnknown:
    """Adapt infra's `reap_deadline` to `ProcessPort`'s contract, the same way `_reap`
    adapts `reap`.
    """
    result = _infra_reap_deadline(pid, deadline)
    return ProcessUnknown() if isinstance(result, _InfraProcessUnknown) else result


_DEFAULT_WAIT_TIMEOUT_S = 30.0
"""How long `run_jail` waits for a jail's process to exit when an embedder gives no
`timeout_s` of its own (TASK-0001.06): long enough for an ordinary jailed command,
short enough that a jailed process which never exits on its own does not hang the
embedder forever.
"""


@dataclass(frozen=True)
class Jail:
    """A bwrap jail an embedder created.

    For bwrap, whose jail is exactly its one process, `process` is all a `Jail` needs; a
    jail type with more to it is a later slice's addition here, not this one's.
    """

    process: Process


@dataclass(frozen=True)
class _RealProcesses:
    """`brig.infra.processes`'s own functions, as the `ProcessPort` an embedder gets by
    default: data (six functions), nothing more, matching the port's shape exactly --
    `reap` and `reap_deadline` through this module's own thin adapters above, which
    translate infra's `ProcessUnknown` into the port's (`ports.py`'s own docstring).
    """

    spawn: Callable[[tuple[str, ...], tuple[int, ...]], SpawnedProcess] = _spawn
    reap: Callable[[int], int | ProcessUnknown] = _reap
    reap_deadline: Callable[[int, float], int | None | ProcessUnknown] = _reap_deadline
    signal_group: Callable[[int, signal.Signals], None] = _signal_group
    reap_nowait: Callable[[int], int | None] = _reap_nowait
    group_alive: Callable[[int], bool] = _group_alive


_processes: ProcessPort = _RealProcesses()


def create_bwrap_jail(command: tuple[str, ...], *, processes: ProcessPort = _processes) -> Jail:
    """Compile `command` into a bwrap jail and start its one process.

    `presentation/drivers/bwrap.py`'s `run` raises `JailSpawnFailed` should the spawn
    fail; nothing in this function's own body raises, so it is not in this docstring.
    """
    plan = bwrap.compile_run(command)
    process = run(operations.create(plan), processes)
    return Jail(process=process)


def run_jail(
    jail: Jail,
    *,
    timeout_s: float = _DEFAULT_WAIT_TIMEOUT_S,
    processes: ProcessPort = _processes,
) -> int:
    """Wait for `jail`'s process to exit and return its exit code.

    Gives up after `timeout_s` seconds (`_DEFAULT_WAIT_TIMEOUT_S` if not given) rather
    than blocking forever on a jailed process that never exits on its own.

    Raises:
        JailWaitTimedOut: the process did not exit within `timeout_s`. Unlike
            `JailSpawnFailed` (nothing was created) or `JailTeardownFailed` (teardown
            already ran), this leaves `jail`'s process still running and unreaped --
            `destroy_jail(jail)` is still required to tear it down.
        JailExitUnknown: the process was no longer this program's child to wait for
            at all by the time the wait ran -- something else, such as an embedder
            that auto-reaps its own children, already collected it first. Unlike
            `JailWaitTimedOut`, retrying this wait can never succeed.
    """
    deadline = time.monotonic() + timeout_s
    exit_code = run(operations.start(jail.process, deadline=deadline), processes)
    if isinstance(exit_code, ExitCodeUnknown):
        raise JailExitUnknown(jail.process)
    if exit_code is None:
        raise JailWaitTimedOut(jail.process)
    return exit_code


def destroy_jail(jail: Jail, *, processes: ProcessPort = _processes) -> None:
    """Tear `jail` down, verified: no process of its group is left when this returns.

    Raises:
        JailTeardownFailed: the kill ladder's last verify still found the group alive.
    """
    state = run(operations.destroy(jail.process), processes)
    if state is not GroupState.GONE:
        raise JailTeardownFailed(jail.process)
