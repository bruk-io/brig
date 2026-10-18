"""brig: a standalone sandbox library. Public surface, re-exported from presentation."""

from brig.presentation.api import Jail, create_bwrap_jail, destroy_jail, run_jail
from brig.presentation.errors import (
    JailExitUnknown,
    JailSpawnFailed,
    JailTeardownFailed,
    JailWaitTimedOut,
)
from brig.presentation.ports import ProcessUnknown

__all__ = [
    "Jail",
    "JailExitUnknown",
    "JailSpawnFailed",
    "JailTeardownFailed",
    "JailWaitTimedOut",
    "ProcessUnknown",
    "create_bwrap_jail",
    "destroy_jail",
    "run_jail",
]
