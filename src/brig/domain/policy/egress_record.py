"""What a running jail's egress did, as data an embedder reads (decision-0009 items 5 and 6): the
grants as created and every change since, and each decision its proxy made. Times enter as data,
read by infra; nothing here reads a clock (rule 2)."""

from dataclasses import dataclass
from datetime import datetime

from brig.domain.policy.egress import (
    Destination,
    EgressChangeKind,
    EgressPolicy,
    EgressReason,
    EgressVerdict,
    egress_after,
)


@dataclass(frozen=True)
class EgressChange:
    """One `allow_egress` or `revoke_egress` a running jail's proxy was sent: `kind`,
    `destination`, and `time`, an aware UTC time, when the host sent it."""

    kind: EgressChangeKind
    destination: Destination
    time: datetime


@dataclass(frozen=True)
class EgressRecord:
    """A jail's egress grants: `created`, the policy it was created with, and `changes`, every
    change sent to its proxy since, in the order sent. What the proxy decides by now is
    `granted_now(record)`."""

    created: EgressPolicy
    changes: tuple[EgressChange, ...] = ()


def granted_now(record: EgressRecord) -> EgressPolicy:
    """The policy `record`'s changes leave, applied in order to what it was created with."""
    policy = record.created
    for change in record.changes:
        policy = egress_after(policy, change.kind, change.destination)
    return policy


@dataclass(frozen=True)
class EgressDecision:
    """One decision a jail's egress proxy made about one request (decision-0009 item 6).

    `seq` is the proxy's own count, from 1, so a gap says decisions were dropped before the
    embedder took them (the link keeps a bounded number). `verdict` is what the proxy did,
    `destination` the host and port the request named, `reason` why, and `time` when the proxy
    decided, an aware UTC time. `line` is the decision exactly as the proxy wrote it: one JSON
    line in brig's envelope (`infra/log.py`), for an embedder that keeps a log of its own to
    write as it is. The library writes it nowhere."""

    seq: int
    verdict: EgressVerdict
    destination: Destination
    reason: EgressReason
    time: datetime
    line: str
