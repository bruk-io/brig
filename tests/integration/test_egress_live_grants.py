"""Integration tests for a running jail's egress (TASK-0001.37, decision-0009 items 5 and 6),
through brig's public API with the proxy faked at infra's edge (`FakeEgress`, on a `Jail` built
directly): a jail with no egress refuses every call with an error that says what to do; a
malformed destination is refused as `check_egress_policy` refuses it, before the proxy is sent
anything; a good change reaches the proxy and the record; decisions are handed back once; and
the report states the policy as created and every change since."""

from datetime import UTC, datetime

import pytest
from tests.integration.fakes import FakeEgress, FakeProcesses, FakeSupervisors

from brig import (
    NETWORK_EGRESS_CLAIM,
    Destination,
    EgressChange,
    EgressChangeKind,
    EgressDecision,
    EgressPolicy,
    EgressReason,
    EgressVerdict,
    Grade,
    Jail,
    JailEgressEnded,
    JailHasNoEgress,
    PolicyEgressCidr,
    PolicyEgressHostInvalid,
    PolicyEgressPortOutOfRange,
    PolicyEgressWildcardMisplaced,
    Process,
    allow_egress,
    create_bwrap_jail,
    destroy_jail,
    egress_decisions,
    egress_record,
    render,
    revoke_egress,
)

_GOOD = Destination("example.com", 443)


def _jail(egress: FakeEgress | None) -> Jail:
    return Jail(process=Process(pid=4000, pgid=4000), supervisors=FakeSupervisors(), egress=egress)


@pytest.mark.parametrize("with_policy", [False, True])
def test_a_jail_with_no_egress_proxy_refuses_every_egress_call(with_policy: bool) -> None:
    """Created without an `EgressPolicy`, or with one but a caller's own `supervisors`, which
    starts no proxy: nothing to grant to or read from, and the error says how to get one."""
    processes, supervisors = FakeProcesses(), FakeSupervisors()
    jail = create_bwrap_jail(
        ("true",),
        egress=EgressPolicy() if with_policy else None,
        processes=processes,
        supervisors=supervisors,
    )
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    for call in (
        lambda: allow_egress(jail, _GOOD),
        lambda: revoke_egress(jail, _GOOD),
        lambda: egress_decisions(jail),
        lambda: egress_record(jail),
    ):
        with pytest.raises(JailHasNoEgress) as raised:
            call()
        assert "egress=EgressPolicy(" in str(raised.value)
        assert " -- " in str(raised.value)


def test_no_egress_is_refused_before_the_destination_is_looked_at() -> None:
    with pytest.raises(JailHasNoEgress):
        allow_egress(_jail(None), Destination("ex_ample.com", 0))


@pytest.mark.parametrize(
    ("destination", "error"),
    [
        (Destination("ex_ample.com", 443), PolicyEgressHostInvalid),
        (Destination("example.com", 0), PolicyEgressPortOutOfRange),
        (Destination("10.0.0.0/8", 443), PolicyEgressCidr),
        (Destination("a.*.example.com", 443), PolicyEgressWildcardMisplaced),
    ],
)
def test_a_malformed_destination_is_refused_before_the_proxy_is_sent_anything(
    destination: Destination, error: type[Exception]
) -> None:
    egress = FakeEgress()
    jail = _jail(egress)

    for call in (allow_egress, revoke_egress):
        with pytest.raises(error) as raised:
            call(jail, destination)
        assert getattr(raised.value, "destination") == destination

    assert egress.changes == []


def test_allow_and_revoke_reach_the_proxy_and_the_record_in_order() -> None:
    egress = FakeEgress(created=EgressPolicy((Destination("pypi.org", 443),)))
    jail = _jail(egress)

    allow_egress(jail, _GOOD)
    revoke_egress(jail, Destination("pypi.org", 443))

    record = egress_record(jail)
    assert record.created == EgressPolicy((Destination("pypi.org", 443),))
    assert record.changes == (
        EgressChange(EgressChangeKind.ALLOW, _GOOD, egress.now),
        EgressChange(EgressChangeKind.REVOKE, Destination("pypi.org", 443), egress.now),
    )


def test_a_change_to_a_proxy_that_has_ended_is_refused_and_not_recorded() -> None:
    egress = FakeEgress(ended=True)

    with pytest.raises(JailEgressEnded) as raised:
        allow_egress(_jail(egress), _GOOD)

    assert raised.value.destination == _GOOD
    assert " -- " in str(raised.value)
    assert egress.changes == []


def test_each_decision_is_handed_back_once() -> None:
    decision = EgressDecision(
        seq=1,
        verdict=EgressVerdict.REFUSED,
        destination=_GOOD,
        reason=EgressReason.NOT_GRANTED,
        address="",
        time=datetime(2026, 11, 4, tzinfo=UTC),
        line="{}",
    )
    egress = FakeEgress(pending=[decision])
    jail = _jail(egress)

    assert list(egress_decisions(jail)) == [decision]
    assert list(egress_decisions(jail)) == []


def test_the_report_states_the_policy_as_created_and_every_change_since() -> None:
    egress = FakeEgress(created=EgressPolicy((Destination("pypi.org", 443),)))
    jail = _jail(egress)
    allow_egress(jail, Destination("::1", 8080))
    revoke_egress(jail, Destination("pypi.org", 443))

    text = render({NETWORK_EGRESS_CLAIM: Grade.BEST_EFFORT}, egress_record(jail))

    assert text.splitlines() == [
        f"network: BEST_EFFORT -- {NETWORK_EGRESS_CLAIM.description}",
        "egress as created: pypi.org:443",
        "egress allow [::1]:8080 at 2026-11-04T05:06:07.000000+00:00",
        "egress revoke pypi.org:443 at 2026-11-04T05:06:07.000000+00:00",
        "egress now: [::1]:8080",
    ]


def test_a_report_with_nothing_granted_says_so() -> None:
    text = render({}, egress_record(_jail(FakeEgress())))

    assert text.splitlines() == [
        "egress as created: nothing (loopback only)",
        "egress now: nothing (loopback only)",
    ]
