"""grade(claims, evidence) -> Mapping[Claim, Grade]: rule 11's one producer of a
report (decision-0001 rule 11; decision-0002 section 4).

A jail type's compile, or an e2e battery wiring an existing claim in for the first
time (TASK-0001.18), produces `Claim`s; neither grades them. An e2e battery that
plants the violation with a positive control (rule 11's own text) is the one source
of `Evidence`; `grade` below is the one place that turns a claim plus whatever
evidence exists for it into the one word a report states. A claim nothing has
measured yet grades `UNENFORCED` -- not a failure, a fact about what has not been
proven -- so a report can never overstate what the library actually knows.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from brig.domain.claims import Claim


class Grade(StrEnum):
    """What a claim's evidence showed: the only three words a report ever states
    (rule 11).
    """

    ENFORCED = "ENFORCED"
    VIOLATED = "VIOLATED"
    UNENFORCED = "UNENFORCED"


@dataclass(frozen=True)
class Evidence:
    """What an e2e battery measured for one claim: whether its positive control was
    observed getting through, and whether its planted violation was blocked.

    Rule 11 asks for "an e2e battery that plants the violation with a positive
    control" -- not a violation alone. `violation_blocked` on its own is not
    evidence: a battery whose probe can never detect anything open (a dead code
    path, a probe that always reports "blocked" by mistake) could set it `True`
    without ever having proven the probe could tell the difference. `grade` below
    reads `violation_blocked` only once `control_observed` confirms the positive
    control -- the same attempt, made with the boundary not yet in place -- was
    actually seen getting through, the same pairing every one of TASK-0001.05's own
    batteries already uses.
    """

    control_observed: bool
    violation_blocked: bool


def grade(claims: tuple[Claim, ...], evidence: Mapping[Claim, Evidence]) -> Mapping[Claim, Grade]:
    """Grade every claim in `claims` from whatever `evidence` has for it.

    A claim with no key in `evidence` -- or one whose positive control was never
    observed getting through -- grades `UNENFORCED`: nothing proved the probe could
    have seen a violation, so nothing here claims it did, per rule 11's own text
    ("a claim without evidence grades unenforced"). Otherwise, a claim whose planted
    violation was blocked grades `ENFORCED`; one whose violation got through anyway
    grades `VIOLATED`. Pure: this module does no I/O (rule 2), so every `Evidence`
    here was measured elsewhere, by whoever calls this.
    """
    report: dict[Claim, Grade] = {}
    for claim in claims:
        found = evidence.get(claim)
        if found is None or not found.control_observed:
            report[claim] = Grade.UNENFORCED
        elif found.violation_blocked:
            report[claim] = Grade.ENFORCED
        else:
            report[claim] = Grade.VIOLATED
    return report
