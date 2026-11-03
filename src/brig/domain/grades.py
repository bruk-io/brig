"""Grades: `grade(claims, evidence)` is the one producer of a graded report (decision-0001
rule 11). Evidence comes only from an e2e battery that plants the violation beside a positive
control; a claim nothing has measured grades `UNENFORCED`."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from brig.domain.claims import Claim


class Grade(StrEnum):
    """What a claim's evidence showed, the only four words a report ever states (rule 11),
    strongest first. `ENFORCED` needs a kernel mechanism that holds the claim, never a list of
    places that found nothing (decision-0008, the 2026-11-03 note). `BEST_EFFORT`: it holds
    unless the host itself changes what the jail sees, as replacing the entry a mask, a deny or a
    nested readable root is mounted on can, or keeping a listening socket under a root."""

    ENFORCED = "ENFORCED"
    BEST_EFFORT = "BEST_EFFORT"
    UNENFORCED = "UNENFORCED"
    VIOLATED = "VIOLATED"


_STRENGTH = frozendict(
    {Grade.VIOLATED: 0, Grade.UNENFORCED: 1, Grade.BEST_EFFORT: 2, Grade.ENFORCED: 3}
)


def at_most(stated: Grade, measured: Grade) -> bool:
    """Whether `stated` claims no more than `measured` shows: what a battery asserts of a
    jail's report against the grade its own evidence earns."""
    return _STRENGTH[stated] <= _STRENGTH[measured]


@dataclass(frozen=True)
class Evidence:
    """What an e2e battery measured for one claim: whether its positive control got through,
    and whether its planted violation was blocked. `violation_blocked` counts only once
    `control_observed` shows the probe could see a violation at all."""

    control_observed: bool
    violation_blocked: bool


def grade(
    claims: tuple[Claim, ...], evidence: Mapping[Claim, Evidence]
) -> frozendict[Claim, Grade]:
    """Grade each of `claims` from its `evidence`: `UNENFORCED` with none, or with a positive
    control never observed; else `ENFORCED` if the violation was blocked, `VIOLATED` if not."""
    report: dict[Claim, Grade] = {}
    for claim in claims:
        found = evidence.get(claim)
        if found is None or not found.control_observed:
            report[claim] = Grade.UNENFORCED
        elif found.violation_blocked:
            report[claim] = Grade.ENFORCED
        else:
            report[claim] = Grade.VIOLATED
    return frozendict(report)
