"""Hypothesis strategies for the unit tier: plain data a pure domain function takes, generated
over the whole of its domain rather than the cases a test author thought of."""

from ipaddress import IPv4Address, IPv6Address

from hypothesis import strategies as st

ports = st.integers(min_value=1, max_value=65535)
"""Every port a grant or a request may name."""

_labels = st.from_regex(r"[a-z0-9]([a-z0-9-]{0,14}[a-z0-9])?", fullmatch=True)
_top_labels = st.from_regex(r"[a-z]([a-z0-9-]{0,8}[a-z0-9])?", fullmatch=True)

hostnames = st.builds(
    lambda labels, top: ".".join((*labels, top)),
    st.lists(_labels, max_size=4),
    _top_labels,
)
"""Valid hostnames, lower-case, with no trailing dot: up to four labels of letters, digits and
inner hyphens under a last label that starts with a letter, so no resolver reads it as a number."""


def _public(address: IPv4Address | IPv6Address) -> bool:
    return address.is_global and not address.is_reserved and not address.is_multicast


public_addresses = st.one_of(
    st.ip_addresses(v=4).filter(_public),
    st.ip_addresses(v=6, network="2000::/3").filter(_public),
).map(str)
"""Globally reachable unicast addresses, as text: what a name may resolve to with no IP grant."""

_PRIVATE_NETWORKS = (
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "0.0.0.0/8",
    "100.64.0.0/10",
    "::1/128",
    "::/128",
    "fe80::/10",
    "fc00::/7",
)

private_addresses = st.one_of(
    *(st.ip_addresses(network=network) for network in _PRIVATE_NETWORKS),
    st.ip_addresses(v=4, network="127.0.0.0/8").map(lambda address: f"::ffff:{address}"),
    st.ip_addresses(v=4, network="10.0.0.0/8").map(lambda address: f"::ffff:{address}"),
).map(str)
"""Addresses no name may reach without an IP grant, as text: loopback, RFC 1918, link-local, the
unspecified and "this network" ranges, shared address space, unique-local, and IPv4-mapped
private."""
