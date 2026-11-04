"""Integration tests for a jail's create with an egress policy (TASK-0001.36), through brig's
public API with the world faked at infra's edge: a malformed `EgressPolicy`, an `EnvPolicy`
naming a proxy variable, or an `EgressLimits` field raised past its default or not above zero
(TASK-0049), is refused before anything starts, with `check_egress_policy`'s and
`check_egress_limits`' errors; a good one sets the proxy variables over the scrubbed
environment; no policy changes nothing."""

import pytest
from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import (
    Destination,
    EgressLimits,
    EgressPolicy,
    EnvPolicy,
    PolicyEgressHostInvalid,
    PolicyEgressLimitOutOfRange,
    PolicyEgressPortOutOfRange,
    PolicyEnvNamesProxyVariable,
    create_bwrap_jail,
    destroy_jail,
)


@pytest.mark.parametrize(
    ("destination", "error"),
    [
        (Destination("ex_ample.com", 443), PolicyEgressHostInvalid),
        (Destination("example.com", 70000), PolicyEgressPortOutOfRange),
    ],
)
def test_a_malformed_egress_policy_is_refused_before_anything_starts(
    destination: Destination, error: type[Exception]
) -> None:
    supervisors = FakeSupervisors()

    with pytest.raises(error) as exc_info:
        create_bwrap_jail(
            ("true",),
            egress=EgressPolicy((destination,)),
            processes=FakeProcesses(),
            supervisors=supervisors,
        )

    assert getattr(exc_info.value, "destination") == destination
    assert supervisors.started == []


@pytest.mark.parametrize(
    ("limits", "name", "value", "ceiling"),
    [
        (EgressLimits(connections=0), "connections", 0, 256),
        (EgressLimits(bridge_connections=257), "bridge_connections", 257, 256),
        (EgressLimits(handshake_s=30.5), "handshake_s", 30.5, 30.0),
        (EgressLimits(handshake_s=0.0), "handshake_s", 0.0, 30.0),
    ],
)
def test_an_egress_limit_raised_past_its_default_or_not_above_zero_is_refused(
    limits: EgressLimits, name: str, value: float, ceiling: float
) -> None:
    supervisors = FakeSupervisors()

    with pytest.raises(PolicyEgressLimitOutOfRange) as exc_info:
        create_bwrap_jail(
            ("true",),
            egress=EgressPolicy(),
            egress_limits=limits,
            processes=FakeProcesses(),
            supervisors=supervisors,
        )

    assert (exc_info.value.name, exc_info.value.value, exc_info.value.ceiling) == (
        name,
        value,
        ceiling,
    )
    assert " -- " in str(exc_info.value)
    assert supervisors.started == []


def test_egress_limits_lowered_to_one_are_accepted() -> None:
    """The floor: each limit may be lowered as far as one connection, or a moment."""
    processes, supervisors = FakeProcesses(), FakeSupervisors()

    jail = create_bwrap_jail(
        ("true",),
        egress=EgressPolicy(),
        egress_limits=EgressLimits(connections=1, bridge_connections=1, handshake_s=0.1),
        processes=processes,
        supervisors=supervisors,
    )
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert len(supervisors.started) == 1


@pytest.mark.parametrize("name", ["HTTPS_PROXY", "no_proxy"])
def test_an_env_policy_naming_a_proxy_variable_is_refused_with_egress(name: str) -> None:
    supervisors = FakeSupervisors()

    with pytest.raises(PolicyEnvNamesProxyVariable) as exc_info:
        create_bwrap_jail(
            ("true",),
            env={name: "http://elsewhere:8080"},
            env_policy=EnvPolicy(allowed=("PATH", name)),
            egress=EgressPolicy(),
            processes=FakeProcesses(),
            supervisors=supervisors,
        )

    assert exc_info.value.name == name
    assert " -- " in str(exc_info.value)
    assert supervisors.started == []


def test_without_egress_a_proxy_variable_passes_as_any_other_name() -> None:
    """No egress policy: behaviour unchanged, so an allowed `HTTPS_PROXY` reaches the command
    like any allowed name, and nothing else is set."""
    processes, supervisors = FakeProcesses(), FakeSupervisors()

    jail = create_bwrap_jail(
        ("true",),
        env={"HTTPS_PROXY": "http://elsewhere:8080"},
        env_policy=EnvPolicy(allowed=("HTTPS_PROXY",)),
        processes=processes,
        supervisors=supervisors,
    )
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert supervisors.started == [
        (("true",), frozendict({"HTTPS_PROXY": "http://elsewhere:8080"}))
    ]


def test_with_egress_the_proxy_variables_are_laid_over_the_scrubbed_env() -> None:
    processes, supervisors = FakeProcesses(), FakeSupervisors()

    jail = create_bwrap_jail(
        ("true",),
        env={"PATH": "/usr/bin", "SECRET": "shh"},
        env_policy=EnvPolicy(allowed=("PATH",)),
        egress=EgressPolicy((Destination("example.com", 443),)),
        processes=processes,
        supervisors=supervisors,
    )
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    ((_, env),) = supervisors.started
    assert env["PATH"] == "/usr/bin"
    assert "SECRET" not in env
    assert env["HTTPS_PROXY"] == env["http_proxy"] == "http://127.0.0.1:3128"
    assert env["ALL_PROXY"] == env["all_proxy"] == "socks5h://127.0.0.1:3128"
    assert env["NO_PROXY"] == env["no_proxy"] == ""
