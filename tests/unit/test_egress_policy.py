"""Unit tests for the egress policy and its decision (decision-0009 items 3 and 4,
`domain/policy/egress.py`): `egress_refusal` over an `EgressPolicy`, `parse_authority` over what
a request names, and `decide_egress`, the whole of what the proxy allows. Plain data in and out,
nothing mocked; Hypothesis where the property holds for every input of a kind."""

from ipaddress import ip_address

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tests.unit.strategies import hostnames, ports, private_addresses, public_addresses

from brig.domain.policy.egress import (
    AddressUnparseable,
    Allowed,
    Authority,
    AuthorityProblem,
    AuthorityUnparseable,
    CidrNotation,
    Destination,
    EgressPolicy,
    EmptyHost,
    InvalidHostname,
    MisplacedWildcard,
    NeedlessBrackets,
    NotGranted,
    PortOutOfRange,
    PrivateAddress,
    Resolve,
    Unresolved,
    decide_egress,
    egress_refusal,
    parse_authority,
)

_PUBLIC = "93.184.215.14"
_PUBLIC_V6 = "2606:2800:21f:cb07:6820:80da:af6b:8b2c"


def _allow(*grants: tuple[str, int]) -> EgressPolicy:
    return EgressPolicy(tuple(Destination(host, port) for host, port in grants))


# the policy: what an embedder may grant


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "Example.COM.",
        "localhost",
        "a-b.c-d.example",
        "xn--bcher-kva.example",
        "1password.com",
        "*.example.com",
        "*.Example.com.",
        "10.0.0.1",
        "::1",
        "::ffff:10.0.0.1",
        "2001:db8::1",
        "a" * 63 + ".com",
    ],
)
def test_every_form_decision_0009_names_is_granted(host: str) -> None:
    assert egress_refusal(_allow((host, 443))) is None


def test_the_empty_policy_is_the_default_and_refuses_nothing_in_itself() -> None:
    assert EgressPolicy() == EgressPolicy(allow=())
    assert egress_refusal(EgressPolicy()) is None


@pytest.mark.parametrize(
    ("host", "refusal"),
    [
        ("", EmptyHost),
        ("[::1]", NeedlessBrackets),
        ("[10.0.0.1]", NeedlessBrackets),
        ("[example.com]", NeedlessBrackets),
        ("10.0.0.0/8", CidrNotation),
        ("10.0.0.1/32", CidrNotation),
        ("fc00::/7", CidrNotation),
        ("*", MisplacedWildcard),
        ("*example.com", MisplacedWildcard),
        ("**.example.com", MisplacedWildcard),
        ("a.*.example.com", MisplacedWildcard),
        ("*.*.example.com", MisplacedWildcard),
        ("example.*", MisplacedWildcard),
        ("example.com/8", InvalidHostname),
        ("*.", InvalidHostname),
        ("*.10.0.0.1", InvalidHostname),
        ("exa mple.com", InvalidHostname),
        (" example.com", InvalidHostname),
        ("ex_ample.com", InvalidHostname),
        ("-example.com", InvalidHostname),
        ("example-.com", InvalidHostname),
        ("example..com", InvalidHostname),
        (".example.com", InvalidHostname),
        ("example.com..", InvalidHostname),
        ("bücher.example", InvalidHostname),
        ("\u212aample.com", InvalidHostname),
        ("a" * 64 + ".com", InvalidHostname),
        (".".join(["a" * 63] * 4), InvalidHostname),
        ("10.1", InvalidHostname),
        ("127.1", InvalidHostname),
        ("010.0.0.1", InvalidHostname),
        ("0x7f000001", InvalidHostname),
        ("example.0x7f", InvalidHostname),
        ("256.0.0.1", InvalidHostname),
        ("fe80::1%eth0", InvalidHostname),
        ("example.com:443", InvalidHostname),
        ("user@example.com", InvalidHostname),
    ],
)
def test_each_malformed_host_is_refused_with_its_own_reason(host: str, refusal: type) -> None:
    destination = Destination(host, 443)

    assert egress_refusal(EgressPolicy((destination,))) == refusal(destination)


@pytest.mark.parametrize("port", [0, -1, 65536, 100000])
def test_a_port_outside_1_to_65535_is_refused(port: int) -> None:
    destination = Destination("example.com", port)

    assert egress_refusal(EgressPolicy((destination,))) == PortOutOfRange(destination)


def test_a_port_that_is_not_a_whole_number_is_refused() -> None:
    """An embedder's data may come from anywhere: `True` and `443.0` compare equal to 1 and 443,
    and neither is a port."""
    for port in (True, 443.0, "443"):
        destination = Destination("example.com", port)  # type: ignore[arg-type]

        assert egress_refusal(EgressPolicy((destination,))) == PortOutOfRange(destination)


def test_the_first_malformed_entry_in_order_is_the_one_named() -> None:
    policy = _allow(("example.com", 443), ("*", 443), ("", 443))

    assert egress_refusal(policy) == MisplacedWildcard(Destination("*", 443))


@given(st.text(), st.integers())
def test_any_destination_is_judged_and_never_raises(host: str, port: int) -> None:
    refusal = egress_refusal(EgressPolicy((Destination(host, port),)))

    assert refusal is None or refusal.destination == Destination(host, port)


@given(hostnames, ports)
def test_every_valid_name_and_its_wildcard_are_granted(name: str, port: int) -> None:
    assert egress_refusal(_allow((name, port), (f"*.{name}", port))) is None


# authorities: what a request names


@pytest.mark.parametrize(
    ("text", "authority"),
    [
        ("example.com:443", Authority("example.com", 443)),
        ("Example.COM.:443", Authority("Example.COM.", 443)),
        ("10.0.0.1:80", Authority("10.0.0.1", 80)),
        ("[::1]:443", Authority("::1", 443)),
        ("[2001:db8::1]:8443", Authority("2001:db8::1", 8443)),
        ("[::ffff:10.0.0.1]:443", Authority("::ffff:10.0.0.1", 443)),
        ("example.com:1", Authority("example.com", 1)),
        ("example.com:65535", Authority("example.com", 65535)),
    ],
)
def test_an_authority_with_a_port_parses(text: str, authority: Authority) -> None:
    assert parse_authority(text) == authority


def test_an_absolute_url_s_authority_takes_the_scheme_s_default_port() -> None:
    assert parse_authority("example.com", default_port=80) == Authority("example.com", 80)
    assert parse_authority("[::1]", default_port=80) == Authority("::1", 80)
    assert parse_authority("example.com:8080", default_port=80) == Authority("example.com", 8080)


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("", AuthorityProblem.EMPTY),
        ("[::1", AuthorityProblem.UNCLOSED_BRACKET),
        ("[::1]443", AuthorityProblem.AFTER_BRACKET),
        ("[::1]x:443", AuthorityProblem.AFTER_BRACKET),
        ("[example.com]:443", AuthorityProblem.BRACKETED_NOT_IPV6),
        ("[10.0.0.1]:443", AuthorityProblem.BRACKETED_NOT_IPV6),
        ("[]:443", AuthorityProblem.BRACKETED_NOT_IPV6),
        ("[fe80::1%25eth0]:443", AuthorityProblem.BRACKETED_NOT_IPV6),
        ("::1:443", AuthorityProblem.BARE_IPV6),
        ("2001:db8::1", AuthorityProblem.BARE_IPV6),
        ("example.com", AuthorityProblem.NO_PORT),
        ("[::1]", AuthorityProblem.NO_PORT),
        ("example.com:", AuthorityProblem.BAD_PORT),
        ("[::1]:", AuthorityProblem.BAD_PORT),
        ("example.com:0", AuthorityProblem.BAD_PORT),
        ("example.com:65536", AuthorityProblem.BAD_PORT),
        ("example.com:443000", AuthorityProblem.BAD_PORT),
        ("example.com:+443", AuthorityProblem.BAD_PORT),
        ("example.com:-1", AuthorityProblem.BAD_PORT),
        ("example.com: 443", AuthorityProblem.BAD_PORT),
        ("example.com:٤٤٣", AuthorityProblem.BAD_PORT),
        ("example.com:http", AuthorityProblem.BAD_PORT),
        (":443", AuthorityProblem.BAD_HOST),
        (" example.com:443", AuthorityProblem.BAD_HOST),
        ("exa mple.com:443", AuthorityProblem.BAD_HOST),
        ("ex_ample.com:443", AuthorityProblem.BAD_HOST),
        ("user@example.com:443", AuthorityProblem.BAD_HOST),
        ("*.example.com:443", AuthorityProblem.BAD_HOST),
        ("127.1:443", AuthorityProblem.BAD_HOST),
        ("0x7f000001:443", AuthorityProblem.BAD_HOST),
        ("010.0.0.1:443", AuthorityProblem.BAD_HOST),
        ("\u212a.example.com:443", AuthorityProblem.BAD_HOST),
        ("\uff11.2.3.4:443", AuthorityProblem.BAD_HOST),
        ("example.com\r\n:443", AuthorityProblem.BAD_HOST),
    ],
)
def test_an_unparseable_authority_is_refused_with_its_problem(
    text: str, problem: AuthorityProblem
) -> None:
    assert parse_authority(text) == AuthorityUnparseable(text, problem)


def test_a_bad_default_port_is_refused_not_used() -> None:
    assert parse_authority("example.com", default_port=0) == AuthorityUnparseable(
        "example.com", AuthorityProblem.BAD_PORT
    )


@given(st.text(), st.one_of(st.none(), st.integers()))
def test_any_text_parses_or_is_refused_and_never_raises(text: str, default: int | None) -> None:
    parsed = parse_authority(text, default)

    assert isinstance(parsed, Authority | AuthorityUnparseable)


@given(hostnames, ports)
def test_a_name_and_port_round_trip(name: str, port: int) -> None:
    assert parse_authority(f"{name}:{port}") == Authority(name, port)


@given(st.ip_addresses(v=6), ports)
def test_a_bracketed_ipv6_literal_and_port_round_trip(address: object, port: int) -> None:
    assert parse_authority(f"[{address}]:{port}") == Authority(str(address), port)


@given(st.ip_addresses(v=4), ports)
def test_an_ipv4_literal_and_port_round_trip(address: object, port: int) -> None:
    assert parse_authority(f"{address}:{port}") == Authority(str(address), port)


# the decision: names


def test_an_exact_name_grant_asks_for_the_name_to_be_resolved_then_allows_it() -> None:
    policy = _allow(("example.com", 443))
    request = Authority("example.com", 443)

    assert decide_egress(policy, request) == Resolve("example.com")
    assert decide_egress(policy, request, (_PUBLIC, _PUBLIC_V6)) == Allowed(
        Destination("example.com", 443), (_PUBLIC, _PUBLIC_V6)
    )


def test_an_ungranted_name_is_refused_before_it_is_resolved() -> None:
    """The proxy resolves only what a grant names, so the jail cannot use the resolver as a way
    out: an ungranted name is `NotGranted` with no `Resolve` first."""
    policy = _allow(("example.com", 443))

    assert decide_egress(policy, Authority("secret.attacker.example", 443)) == NotGranted(
        Authority("secret.attacker.example", 443)
    )


@pytest.mark.parametrize("name", ["a.example.com", "a.b.example.com", "A.Example.COM."])
def test_a_suffix_grant_matches_names_under_it(name: str) -> None:
    policy = _allow(("*.example.com", 443))
    request = Authority(name, 443)

    assert decide_egress(policy, request) == Resolve(name.lower().removesuffix("."))
    assert decide_egress(policy, request, (_PUBLIC,)) == Allowed(
        Destination("*.example.com", 443), (_PUBLIC,)
    )


@pytest.mark.parametrize(
    "name",
    [
        "example.com",
        "example.com.",
        "EXAMPLE.com",
        "evilexample.com",
        "example.com.evil.net",
        "aexample.com",
        "example.co",
        "com",
    ],
)
def test_a_suffix_grant_does_not_match_the_suffix_or_a_lookalike(name: str) -> None:
    policy = _allow(("*.example.com", 443))

    assert decide_egress(policy, Authority(name, 443), (_PUBLIC,)) == NotGranted(
        Authority(name, 443)
    )


@pytest.mark.parametrize(
    "name", ["a.example.com", "example.com.evil.net", "evilexample.com", "example.co"]
)
def test_an_exact_grant_matches_only_its_own_name(name: str) -> None:
    policy = _allow(("example.com", 443))

    assert decide_egress(policy, Authority(name, 443), (_PUBLIC,)) == NotGranted(
        Authority(name, 443)
    )


def test_both_grants_together_allow_the_site_and_its_subdomains() -> None:
    policy = _allow(("example.com", 443), ("*.example.com", 443))

    for name in ("example.com", "www.example.com"):
        assert isinstance(decide_egress(policy, Authority(name, 443), (_PUBLIC,)), Allowed)


@pytest.mark.parametrize(
    ("grant", "request_host"),
    [
        ("example.com", "EXAMPLE.COM"),
        ("example.com", "example.com."),
        ("Example.Com.", "example.com"),
        ("EXAMPLE.COM.", "Example.com."),
        ("*.EXAMPLE.com.", "www.example.COM"),
    ],
)
def test_names_compare_without_case_or_one_trailing_dot(grant: str, request_host: str) -> None:
    decided = decide_egress(_allow((grant, 443)), Authority(request_host, 443), (_PUBLIC,))

    assert decided == Allowed(Destination(grant, 443), (_PUBLIC,))


@given(hostnames, ports, ports)
def test_a_name_granted_on_one_port_is_refused_on_any_other(
    name: str, granted: int, requested: int
) -> None:
    policy = _allow((name, granted), (f"*.{name}", granted))
    for host in (name, f"www.{name}"):
        request = Authority(host, requested)
        decided = decide_egress(policy, request, (_PUBLIC,))

        if requested == granted:
            assert isinstance(decided, Allowed)
        else:
            assert decided == NotGranted(request)


@given(hostnames, ports, st.lists(public_addresses, min_size=1, max_size=4))
def test_a_granted_name_resolving_to_public_addresses_is_allowed_to_each(
    name: str, port: int, resolved: list[str]
) -> None:
    decided = decide_egress(_allow((name, port)), Authority(name, port), tuple(resolved))

    assert isinstance(decided, Allowed)
    assert decided.grant == Destination(name, port)
    assert len(decided.addresses) == len(resolved)


@given(hostnames, ports)
def test_a_granted_name_is_resolved_first_never_allowed_unresolved(name: str, port: int) -> None:
    assert decide_egress(_allow((name, port)), Authority(name.upper(), port)) == Resolve(name)


def test_a_name_that_resolved_to_nothing_is_refused() -> None:
    request = Authority("example.com", 443)

    assert decide_egress(_allow(("example.com", 443)), request, ()) == Unresolved(request)


@pytest.mark.parametrize("address", ["", "example.com", "10.0.0", "::g", "[::1]"])
def test_a_name_that_resolved_to_something_not_an_address_is_refused(address: str) -> None:
    request = Authority("example.com", 443)

    assert decide_egress(
        _allow(("example.com", 443)), request, (_PUBLIC, address)
    ) == AddressUnparseable(request, address)


@given(hostnames, ports)
def test_the_empty_policy_refuses_every_request(name: str, port: int) -> None:
    for host in (name, _PUBLIC, "::1"):
        request = Authority(host, port)

        assert decide_egress(EgressPolicy(), request, (_PUBLIC,)) == NotGranted(request)


# the decision: private addresses


_PRIVATE = [
    "127.0.0.1",
    "127.255.255.254",
    "10.0.0.1",
    "10.255.255.255",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "169.254.169.254",
    "169.254.0.1",
    "0.0.0.0",
    "0.1.2.3",
    "100.64.0.1",
    "255.255.255.255",
    "224.0.0.1",
    "240.0.0.1",
    "::1",
    "::",
    "fe80::1",
    "febf::1",
    "fc00::1",
    "fd00:ec2::254",
    "fec0::1",
    "ff02::1",
    "::ffff:127.0.0.1",
    "::ffff:10.0.0.1",
    "::ffff:169.254.169.254",
    "::127.0.0.1",
    "64:ff9b::7f00:1",
    "64:ff9b::a9fe:a9fe",
    "64:ff9b:1::1",
    "2002:7f00:1::",
    "2002:808:808::",
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",
    "2001::1",
    "2001:db8::1",
]


@pytest.mark.parametrize("address", _PRIVATE)
def test_a_name_resolving_to_a_private_address_is_refused_without_an_ip_grant(
    address: str,
) -> None:
    request = Authority("example.com", 443)

    assert decide_egress(_allow(("example.com", 443)), request, (address,)) == PrivateAddress(
        request, address
    )


@pytest.mark.parametrize("address", _PRIVATE)
def test_a_name_resolving_to_a_private_address_is_allowed_with_an_ip_grant_of_it(
    address: str,
) -> None:
    request = Authority("example.com", 443)
    policy = _allow(("example.com", 443), (address, 443))

    decided = decide_egress(policy, request, (address,))

    assert isinstance(decided, Allowed)
    assert decided.grant == Destination("example.com", 443)
    parsed = ip_address(address)
    assert decided.addresses == (str(getattr(parsed, "ipv4_mapped", None) or parsed),)


@pytest.mark.parametrize("address", _PRIVATE)
def test_an_ip_grant_of_a_private_address_on_another_port_does_not_open_it(address: str) -> None:
    request = Authority("example.com", 443)
    policy = _allow(("example.com", 443), (address, 8443))

    assert decide_egress(policy, request, (address,)) == PrivateAddress(request, address)


def test_an_ip_grant_opens_only_the_exact_address_it_names() -> None:
    request = Authority("example.com", 443)
    policy = _allow(("example.com", 443), ("127.0.0.1", 443))

    assert decide_egress(policy, request, ("127.0.0.2",)) == PrivateAddress(request, "127.0.0.2")
    assert decide_egress(policy, request, ("::1",)) == PrivateAddress(request, "::1")


def test_an_ipv4_mapped_address_is_the_ipv4_address_it_maps() -> None:
    """`::ffff:10.0.0.1` reaches 10.0.0.1 on a dual-stack socket, so it is judged, granted and
    connected to as that address."""
    request = Authority("example.com", 443)

    for grant, resolved in (("10.0.0.1", "::ffff:10.0.0.1"), ("::ffff:10.0.0.1", "10.0.0.1")):
        policy = _allow(("example.com", 443), (grant, 443))

        assert decide_egress(policy, request, (resolved,)) == Allowed(
            Destination("example.com", 443), ("10.0.0.1",)
        )


def test_a_nat64_address_is_judged_as_the_ipv4_address_it_carries() -> None:
    request = Authority("example.com", 443)
    policy = _allow(("example.com", 443))

    assert decide_egress(policy, request, ("64:ff9b::5db8:d70e",)) == Allowed(
        Destination("example.com", 443), ("64:ff9b::5db8:d70e",)
    )
    assert decide_egress(policy, request, ("64:ff9b::7f00:1",)) == PrivateAddress(
        request, "64:ff9b::7f00:1"
    )


def test_a_zoned_link_local_address_is_refused_and_no_grant_can_open_it() -> None:
    request = Authority("example.com", 443)
    policy = _allow(("example.com", 443), ("fe80::1", 443))

    assert decide_egress(policy, request, ("fe80::1%eth0",)) == PrivateAddress(
        request, "fe80::1%eth0"
    )


def test_one_of_the_host_s_own_addresses_is_refused_though_it_is_public() -> None:
    """decision-0009 item 4: a name that resolves to the jail's own host reaches its services,
    so the host's addresses are never public to a name, only to an IP grant naming them."""
    request = Authority("example.com", 443)
    host = (_PUBLIC, "::ffff:not-an-address")

    assert decide_egress(_allow(("example.com", 443)), request, (_PUBLIC,), host) == (
        PrivateAddress(request, _PUBLIC)
    )
    opened = _allow(("example.com", 443), (_PUBLIC, 443))
    assert decide_egress(opened, request, (_PUBLIC,), host) == Allowed(
        Destination("example.com", 443), (_PUBLIC,)
    )


@given(
    hostnames,
    ports,
    st.lists(public_addresses, max_size=4),
    private_addresses,
    st.integers(min_value=0, max_value=4),
)
def test_a_name_resolving_to_any_private_address_among_public_ones_is_refused(
    name: str, port: int, public: list[str], private: str, at: int
) -> None:
    resolved = (*public[:at], private, *public[at:])
    request = Authority(name, port)

    assert decide_egress(_allow((name, port)), request, resolved) == PrivateAddress(
        request, private
    )


@given(hostnames, ports, private_addresses)
def test_any_private_address_is_refused_without_a_grant_and_allowed_with_one(
    name: str, port: int, private: str
) -> None:
    request = Authority(name, port)

    assert decide_egress(_allow((name, port)), request, (private,)) == PrivateAddress(
        request, private
    )
    granted = decide_egress(_allow((name, port), (private, port)), request, (private,))
    assert isinstance(granted, Allowed)
    assert granted.grant == Destination(name, port)


# the decision: IP literals


@pytest.mark.parametrize(
    ("grant", "requested", "connect"),
    [
        ("10.0.0.1", "10.0.0.1", "10.0.0.1"),
        ("127.0.0.1", "127.0.0.1", "127.0.0.1"),
        ("169.254.169.254", "169.254.169.254", "169.254.169.254"),
        ("::1", "::1", "::1"),
        ("::1", "0:0:0:0:0:0:0:1", "::1"),
        ("0:0:0:0:0:0:0:1", "::1", "::1"),
        ("2001:DB8::1", "2001:db8::1", "2001:db8::1"),
        ("10.0.0.1", "::ffff:10.0.0.1", "10.0.0.1"),
        (_PUBLIC, _PUBLIC, _PUBLIC),
    ],
)
def test_a_literal_grant_allows_a_request_naming_that_address(
    grant: str, requested: str, connect: str
) -> None:
    decided = decide_egress(_allow((grant, 443)), Authority(requested, 443))

    assert decided == Allowed(Destination(grant, 443), (connect,))


def test_a_literal_request_through_brackets_matches_its_grant() -> None:
    request = parse_authority("[::1]:443")
    assert isinstance(request, Authority)

    assert decide_egress(_allow(("::1", 443)), request) == Allowed(
        Destination("::1", 443), ("::1",)
    )


def test_a_literal_request_is_refused_without_a_literal_grant_of_it() -> None:
    policy = _allow(("10.0.0.1", 443), ("example.com", 443), ("*.example.com", 443))

    for host in ("10.0.0.2", "127.0.0.1", "169.254.169.254", "::1", _PUBLIC):
        request = Authority(host, 443)

        assert decide_egress(policy, request, (host,)) == NotGranted(request)


def test_a_literal_grant_on_another_port_refuses_the_request() -> None:
    request = Authority("10.0.0.1", 443)

    assert decide_egress(_allow(("10.0.0.1", 80)), request) == NotGranted(request)


def test_a_name_grant_never_matches_a_literal_whatever_it_resolves_to() -> None:
    request = Authority(_PUBLIC, 443)

    assert decide_egress(_allow(("example.com", 443)), request, (_PUBLIC,)) == NotGranted(request)


@given(st.ip_addresses(), ports, ports)
def test_any_literal_is_allowed_only_on_its_granted_port(
    address: object, granted: int, requested: int
) -> None:
    request = Authority(str(address), requested)
    decided = decide_egress(_allow((str(address), granted)), request)

    if requested == granted:
        assert isinstance(decided, Allowed)
    else:
        assert decided == NotGranted(request)


# the decision: what it refuses to read


@pytest.mark.parametrize(
    "host",
    ["", "[::1]", "*.example.com", "exa mple.com", "127.1", "0x7f000001", "fe80::1%eth0", "a/b"],
)
def test_a_request_host_that_is_no_name_or_literal_is_refused(host: str) -> None:
    policy = _allow(("*.example.com", 443), ("::1", 443), ("fe80::1", 443))

    assert decide_egress(policy, Authority(host, 443), (_PUBLIC,)) == AuthorityUnparseable(
        host, AuthorityProblem.BAD_HOST
    )


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_a_request_port_outside_1_to_65535_is_refused(port: int) -> None:
    """A SOCKS5 request carries its port as two bytes, so port 0 can arrive."""
    assert decide_egress(_allow(("example.com", port)), Authority("example.com", port)) == (
        AuthorityUnparseable(str(port), AuthorityProblem.BAD_PORT)
    )


def test_a_malformed_grant_matches_nothing() -> None:
    """`egress_refusal` refuses these at create; if one reaches the decision, it opens
    nothing."""
    policy = _allow(("[::1]", 443), ("127.0.0.0/8", 443), ("example.com", 0), ("*", 443))

    assert decide_egress(policy, Authority("::1", 443)) == NotGranted(Authority("::1", 443))
    assert decide_egress(policy, Authority("127.0.0.1", 443)) == NotGranted(
        Authority("127.0.0.1", 443)
    )
    assert decide_egress(policy, Authority("anything.example", 443)) == NotGranted(
        Authority("anything.example", 443)
    )


@given(
    st.lists(st.builds(Destination, st.text(max_size=20), st.integers()), max_size=4),
    st.builds(Authority, st.text(max_size=20), st.integers()),
    st.one_of(st.none(), st.lists(st.text(max_size=40), max_size=4).map(tuple)),
    st.lists(st.text(max_size=40), max_size=2).map(tuple),
)
def test_any_request_against_any_policy_is_decided_and_never_raises(
    allow: list[Destination],
    request: Authority,
    resolved: tuple[str, ...] | None,
    host_addresses: tuple[str, ...],
) -> None:
    decided = decide_egress(EgressPolicy(tuple(allow)), request, resolved, host_addresses)

    if isinstance(decided, Allowed):
        assert decided.grant in allow
        assert decided.grant.port == request.port


def test_the_decision_is_deterministic_and_leaves_its_arguments_alone() -> None:
    policy = _allow(("example.com", 443), ("10.0.0.1", 443))
    request = Authority("example.com", 443)
    resolved = ("10.0.0.1", _PUBLIC)

    first = decide_egress(policy, request, resolved)

    assert decide_egress(policy, request, resolved) == first
    assert policy == _allow(("example.com", 443), ("10.0.0.1", 443))
    assert first == Allowed(Destination("example.com", 443), ("10.0.0.1", _PUBLIC))
