"""A jail's report as text for someone to read. Returned, never printed (rule 14)."""

from collections.abc import Mapping

from brig.domain.claims import Claim
from brig.domain.grades import Grade
from brig.domain.policy.egress import Destination, EgressPolicy
from brig.domain.policy.egress_record import EgressRecord, granted_now


def _named(destination: Destination) -> str:
    host = destination.host
    return f"[{host}]:{destination.port}" if ":" in host else f"{host}:{destination.port}"


def _grants(policy: EgressPolicy) -> str:
    if not policy.allow:
        return "nothing (loopback only)"
    return ", ".join(_named(destination) for destination in policy.allow)


def render(report: Mapping[Claim, Grade], egress: EgressRecord | None = None) -> str:
    """`report` as one line per claim, "<name>: <grade> -- <description>", in its order. With
    `egress` (`egress_record(jail)`), the jail's egress grants follow (decision-0009 item 5): the
    policy as created, every change since, one line each with when it was sent (UTC), and what
    is granted now."""
    lines = [f"{claim.name}: {grade} -- {claim.description}" for claim, grade in report.items()]
    if egress is not None:
        lines.append(f"egress as created: {_grants(egress.created)}")
        lines.extend(
            f"egress {change.kind.value} {_named(change.destination)} at "
            f"{change.time.isoformat(timespec='microseconds')}"
            for change in egress.changes
        )
        lines.append(f"egress now: {_grants(granted_now(egress))}")
    return "\n".join(lines)
