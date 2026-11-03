"""brig: a standalone sandbox library. The whole public surface: presentation's API and errors,
and the domain's plain data an embedder writes or reads (the policies, channels, claims and
grades). An e2e battery may import this and `brig.infra` only (decision-0001 rule 4)."""

from brig.domain.channels import Channel, ChannelDirectory, Reservation, Reservations
from brig.domain.claims import Claim
from brig.domain.grades import Evidence, Grade, grade
from brig.domain.jail_types.bwrap import (
    CHANNEL_EXCLUSIVITY_CLAIM,
    declared_channel_paths,
    writable_shared_paths,
)
from brig.domain.policy.env import DENY_ALL, EnvPolicy
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, FsPolicy
from brig.presentation.api import (
    await_channel_ready,
    destroy_jail,
    interrupt_jail,
    reserve_channels,
    run_jail,
)
from brig.presentation.drivers.bwrap import create_bwrap_jail
from brig.presentation.errors import (
    ChannelDirectoryCreateFailed,
    ChannelNameRefused,
    ChannelNamespaceNotFound,
    JailExitUnknown,
    JailSpawnFailed,
    JailTeardownFailed,
    JailWaitTimedOut,
    PolicyMaskHides,
    PolicyPathNotAbsolute,
    PolicyPathThroughLink,
    PolicyRootAbsent,
    StateDirectoryInvalid,
)
from brig.presentation.jail import Jail
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
    "CHANNEL_EXCLUSIVITY_CLAIM",
    "Channel",
    "ChannelDirectory",
    "ChannelDirectoryPort",
    "ChannelDirectoryCreateFailed",
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
    "PolicyMaskHides",
    "PolicyPathNotAbsolute",
    "PolicyPathThroughLink",
    "PolicyRootAbsent",
    "ProcessUnknown",
    "Reservation",
    "Reservations",
    "StateDirectoryInvalid",
    "SupervisorDoneUnknown",
    "WHOLE_HOST_READ_ONLY",
    "await_channel_ready",
    "create_bwrap_jail",
    "declared_channel_paths",
    "destroy_jail",
    "grade",
    "interrupt_jail",
    "render",
    "reserve_channels",
    "run_jail",
    "writable_shared_paths",
]
