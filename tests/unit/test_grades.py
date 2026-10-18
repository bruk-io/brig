"""Unit test for `grade` (decision-0001 rule 11; TASK-0001.18's proof).

Drives `grade` with fabricated `Claim`s and `Evidence`, nothing real -- the function
is pure, so a plain pair of booleans is enough to prove every branch rule 11 names:
no evidence at all, evidence whose positive control was never observed, evidence
whose planted violation was blocked, and evidence whose planted violation got
through.
"""

from brig.domain.claims import Claim
from brig.domain.grades import Evidence, Grade, grade

_CLAIM = Claim(name="example", description="an example claim for this test only")


def test_a_claim_with_no_evidence_grades_unenforced() -> None:
    """Rule 11's own text: "a claim without evidence grades unenforced.\""""
    assert grade((_CLAIM,), {}) == {_CLAIM: Grade.UNENFORCED}


def test_a_claim_whose_positive_control_was_never_observed_grades_unenforced() -> None:
    """Evidence that never proved the probe could see a violation get through is no
    evidence at all, even where `violation_blocked` says `True`: nothing here lets a
    probe that cannot detect anything claim strength it never measured (rule 11's
    "with a positive control").
    """
    evidence = {_CLAIM: Evidence(control_observed=False, violation_blocked=True)}
    assert grade((_CLAIM,), evidence) == {_CLAIM: Grade.UNENFORCED}


def test_a_claim_with_its_violation_blocked_under_an_observed_control_grades_enforced() -> None:
    evidence = {_CLAIM: Evidence(control_observed=True, violation_blocked=True)}
    assert grade((_CLAIM,), evidence) == {_CLAIM: Grade.ENFORCED}


def test_a_claim_whose_violation_got_through_under_an_observed_control_grades_violated() -> None:
    evidence = {_CLAIM: Evidence(control_observed=True, violation_blocked=False)}
    assert grade((_CLAIM,), evidence) == {_CLAIM: Grade.VIOLATED}


def test_grades_several_claims_independently() -> None:
    """Each claim's grade depends only on its own evidence, never another claim's."""
    enforced_claim = Claim(name="enforced", description="")
    unenforced_claim = Claim(name="unenforced", description="")
    violated_claim = Claim(name="violated", description="")
    evidence = {
        enforced_claim: Evidence(control_observed=True, violation_blocked=True),
        violated_claim: Evidence(control_observed=True, violation_blocked=False),
    }

    report = grade((enforced_claim, unenforced_claim, violated_claim), evidence)

    assert report == {
        enforced_claim: Grade.ENFORCED,
        unenforced_claim: Grade.UNENFORCED,
        violated_claim: Grade.VIOLATED,
    }
