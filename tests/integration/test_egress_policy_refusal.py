"""Integration tests for the egress policy's refusal through the public API (decision-0009 item 3):
`check_egress_policy` translates each domain refusal into brig's own error, naming the entry, and
lets a well-formed policy through."""

import pytest

from brig import (
    Destination,
    EgressPolicy,
    PolicyEgressCidr,
    PolicyEgressHostEmpty,
    PolicyEgressHostInvalid,
    PolicyEgressNeedlessBrackets,
    PolicyEgressPortOutOfRange,
    PolicyEgressWildcardMisplaced,
    check_egress_policy,
)


@pytest.mark.parametrize(
    ("destination", "error"),
    [
        (Destination("", 443), PolicyEgressHostEmpty),
        (Destination("example.com", 0), PolicyEgressPortOutOfRange),
        (Destination("a.*.example.com", 443), PolicyEgressWildcardMisplaced),
        (Destination("10.0.0.0/8", 443), PolicyEgressCidr),
        (Destination("ex_ample.com", 443), PolicyEgressHostInvalid),
        (Destination("[::1]", 443), PolicyEgressNeedlessBrackets),
    ],
)
def test_each_malformed_entry_raises_its_own_error_naming_it(
    destination: Destination,
    error: type[Exception],
) -> None:
    policy = EgressPolicy((Destination("example.com", 443), destination))

    with pytest.raises(error) as exc_info:
        check_egress_policy(policy)

    assert getattr(exc_info.value, "destination") == destination
    assert " -- " in str(exc_info.value)


def test_a_well_formed_policy_passes() -> None:
    policy = EgressPolicy(
        (
            Destination("example.com", 443),
            Destination("*.example.com", 443),
            Destination("10.0.0.1", 5432),
            Destination("::1", 8080),
        )
    )

    check_egress_policy(policy)
    check_egress_policy(EgressPolicy())
