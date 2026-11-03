"""What a jail type's compile claims to enforce (decision-0001 rule 11): a claim, never a
grade. `domain/grades.py` grades claims from evidence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    """One property a jail type's compile states its jail enforces: `name`, one word unique
    within a report (rule 12), and `description`, what it asserts. Hashable, so a report
    keys on it."""

    name: str
    description: str
