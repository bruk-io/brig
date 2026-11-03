"""A jail's report as text for someone to read. Returned, never printed (rule 14)."""

from collections.abc import Mapping

from brig.domain.claims import Claim
from brig.domain.grades import Grade


def render(report: Mapping[Claim, Grade]) -> str:
    """`report` as one line per claim, "<name>: <grade> -- <description>", in its order."""
    return "\n".join(
        f"{claim.name}: {grade} -- {claim.description}" for claim, grade in report.items()
    )
