"""brig: a standalone sandbox library. Public surface, re-exported from presentation,
plus `Claim`/`Evidence`/`Grade`/`grade`, `Bind`/`FsPolicy`/`WHOLE_HOST_READ_ONLY`, and
`DENY_ALL`/`EnvPolicy`, and the channel data (`Channel`, `ChannelDirectory`,
`Reservation`, `Reservations`) straight from `domain` (TASK-0001.18, TASK-0001.16,
TASK-0001.17, TASK-0001.25) -- and, since TASK-0001.27, `await_channel_ready` with
its outcome and refusal types, which are `presentation`'s own. The layout's own
description of this module is "re-exports presentation's api"; grading's four names
and both policies' names are pure data
(and, for `grade`, a pure function) with nothing of infra behind them to wrap, so
routing them through a presentation module first would add an import with no job --
`presentation/report.py`'s `render` is presentation's own real work here, and is
re-exported from there, the same as everything else below it.

TASK-0001.28: `CHANNEL_EXCLUSIVITY_CLAIM` joins that list, straight from
`domain.jail_types.bwrap` -- the module whose own `compile_supervisor_launch` states it
(AC#1: bwrap's compile states the claim, not a battery inventing one), the same
"pure data with nothing of infra behind it" reasoning `WHOLE_HOST_READ_ONLY` above
already follows. Reading a report must not need a second, look-alike `Claim` value:
`Claim` is compared by both fields, so the value a report is keyed by has to be the
one the compile states, and this is how an embedder reaches it.

`writable_shared_paths` and `declared_channel_paths` come with it, from the same
module: they are the two pure functions that say what the claim is *about* (the
enumeration AC#2 asks for, and what that enumeration is compared against), and an
embedder grading the claim from its own measurements needs the same ones. They are
re-exported here rather than reached for at `brig.domain.jail_types.bwrap` directly
because decision-0001 rule 4 gives an e2e battery only two doors into the library,
`brig` and a `brig.infra` module -- the battery that grades this claim is e2e, and
these are the functions it grades it with.
"""

from brig.domain.channels import Channel, ChannelDirectory, Reservation, Reservations
from brig.domain.claims import Claim
from brig.domain.grades import Evidence, Grade, grade
from brig.domain.jail_types.bwrap import (
    CHANNEL_EXCLUSIVITY_CLAIM,
    declared_channel_paths,
    writable_shared_paths,
)
from brig.domain.policy.env import DENY_ALL, EnvPolicy
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, Bind, FsPolicy
from brig.presentation.api import (
    Jail,
    await_channel_ready,
    create_bwrap_jail,
    destroy_jail,
    reserve_channels,
    run_jail,
)
from brig.presentation.errors import (
    ChannelDirectoryCreateFailed,
    ChannelDirectoryUnreachable,
    ChannelNameRefused,
    ChannelNamespaceNotFound,
    JailExitUnknown,
    JailSpawnFailed,
    JailTeardownFailed,
    JailWaitTimedOut,
    StateDirectoryInvalid,
    StateDirectoryUnreachable,
)
from brig.presentation.ports import (
    ChannelDirectoryPort,
    ChannelJailFinished,
    ChannelNotReady,
    ChannelReadinessPort,
    ChannelReadinessRefusal,
    ChannelReady,
    ChannelRefused,
    ProcessUnknown,
    SupervisorDoneUnknown,
)
from brig.presentation.report import render

__all__ = [
    "Bind",
    "CHANNEL_EXCLUSIVITY_CLAIM",
    "Channel",
    "ChannelDirectory",
    "ChannelDirectoryPort",
    "ChannelDirectoryCreateFailed",
    "ChannelDirectoryUnreachable",
    "ChannelJailFinished",
    "ChannelNameRefused",
    "ChannelNamespaceNotFound",
    "ChannelNotReady",
    "ChannelReadinessPort",
    "ChannelReadinessRefusal",
    "ChannelReady",
    "ChannelRefused",
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
    "Reservation",
    "Reservations",
    "StateDirectoryInvalid",
    "StateDirectoryUnreachable",
    "SupervisorDoneUnknown",
    "WHOLE_HOST_READ_ONLY",
    "await_channel_ready",
    "create_bwrap_jail",
    "declared_channel_paths",
    "destroy_jail",
    "grade",
    "render",
    "reserve_channels",
    "run_jail",
    "writable_shared_paths",
]
