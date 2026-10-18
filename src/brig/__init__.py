"""brig: a standalone sandbox library. Public surface, re-exported from presentation,
plus `Claim`/`Evidence`/`Grade`/`grade`, `Bind`/`FsPolicy`/`WHOLE_HOST_READ_ONLY`, and
`DENY_ALL`/`EnvPolicy` straight from `domain` (TASK-0001.18, TASK-0001.16,
TASK-0001.17). The layout's own description of this module is "re-exports
presentation's api"; grading's four names and both policies' names are pure data
(and, for `grade`, a pure function) with nothing of infra behind them to wrap, so
routing them through a presentation module first would add an import with no job --
`presentation/report.py`'s `render` is presentation's own real work here, and is
re-exported from there, the same as everything else below it.
"""

from brig.domain.claims import Claim
from brig.domain.grades import Evidence, Grade, grade
from brig.domain.policy.env import DENY_ALL, EnvPolicy
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, Bind, FsPolicy
from brig.presentation.api import Jail, create_bwrap_jail, destroy_jail, run_jail
from brig.presentation.errors import (
    JailExitUnknown,
    JailSpawnFailed,
    JailTeardownFailed,
    JailWaitTimedOut,
)
from brig.presentation.ports import ProcessUnknown, SupervisorDoneUnknown
from brig.presentation.report import render

__all__ = [
    "Bind",
    "Claim",
    "DENY_ALL",
    "EnvPolicy",
    "Evidence",
    "FsPolicy",
    "Grade",
    "Jail",
    "JailExitUnknown",
    "JailSpawnFailed",
    "JailTeardownFailed",
    "JailWaitTimedOut",
    "ProcessUnknown",
    "SupervisorDoneUnknown",
    "WHOLE_HOST_READ_ONLY",
    "create_bwrap_jail",
    "destroy_jail",
    "grade",
    "render",
    "run_jail",
]
