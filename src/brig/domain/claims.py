"""What a jail type's compile claims to enforce (decision-0001 rule 11): a claim,
never a grade.

A jail type's compile (`domain/jail_types/<type>.py`) states its claims as plain data;
nothing here decides whether a claim holds -- that is `domain/grades.py`'s `grade`,
the one function rule 11 names as the producer of a report, fed by `Evidence` an e2e
battery measured. This module names the claim shape only, so a jail type's compile
and a battery's evidence agree on what claim each refers to without either importing
the other.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    """One property a jail type's compile states its jail enforces.

    `name` is the claim's one word, unique within whatever set of claims a report
    grades together (rule 12); `description` is what it asserts, for a report to show
    someone who was not there when it was written. Hashable and comparable by both
    fields, like every frozen dataclass, so `domain/grades.py`'s `grade` can use a
    `Claim` as a mapping key without a separate identifier.
    """

    name: str
    description: str
