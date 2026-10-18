"""Render a grade report for someone to read (decision-0001 rule 11; TASK-0001.18
AC#2).

Presentation is the only layer that knows both domain and infra (decision-0001); this
module knows domain's `Claim` and `Grade` to format them, and nothing of infra -- it
does no I/O of its own. Rule 14 (the library logs nothing on its own) applies to this
module too: `render` only returns a string, and whoever calls it decides whether to
print it, log it, or hand it back through an embedder's own channel.
"""

from collections.abc import Mapping

from brig.domain.claims import Claim
from brig.domain.grades import Grade


def render(report: Mapping[Claim, Grade]) -> str:
    """Render `report` as one line per claim: "<name>: <grade> -- <description>".

    No ordering of its own: a `Mapping`'s iteration order is whatever its caller
    built, and nothing here second-guesses that -- a caller that wants claims sorted
    or grouped does so itself before calling this.
    """
    return "\n".join(
        f"{claim.name}: {grade} -- {claim.description}" for claim, grade in report.items()
    )
