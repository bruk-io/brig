"""Which destinations a jail may reach through its egress proxy: what the embedder grants, and the
pure decision over one request (decision-0009 items 3 and 4). Plain data and the pure checks over
it (rule 2); the proxy that asks is TASK-0001.36's.

A grant is a `Destination`: a host and a port, the port always required. The host is one of three
forms: an exact hostname (`example.com`), `*.suffix` (any name under the suffix, never the suffix
itself), or an exact IPv4 or IPv6 literal (`10.0.0.1`, `::1`). There are no port wildcards and no
CIDR ranges. Names compare case-insensitively, one trailing dot ignored; literals compare by value,
an IPv4-mapped IPv6 address (`::ffff:10.0.0.1`) as the IPv4 address it maps.

The decision runs in two passes, so a name no grant matches is never looked up (a lookup the jail
can steer is a channel out through the resolver): `decide_egress` without `resolved` either
refuses, allows a literal, or answers `Resolve`; the caller resolves the name and asks again with
what it got back. A name is then allowed only if every address it resolved to is public, or named
exactly, with the same port, by an IP-literal grant: a name that resolves into the host's own
networks reaches nothing a literal grant did not open (the old brig's filter allowed by name alone,
old SPEC decisions 133 and 134; this is decision-0009 item 4's tightening).
"""

from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address, IPv6Network, ip_address, ip_network
from string import hexdigits
from typing import assert_never

type _Address = IPv4Address | IPv6Address


@dataclass(frozen=True)
class Destination:
    """One place a jail may reach: `host` (an exact hostname, `*.suffix`, or an unbracketed IPv4
    or IPv6 literal) and `port` (1 to 65535). A destination is also what an embedder grants or
    revokes while the jail runs (decision-0009 item 5)."""

    host: str
    port: int


@dataclass(frozen=True)
class EgressPolicy:
    """Every destination a jail's command may reach through its proxy. The default, an empty
    `allow`, is loopback inside the jail and nothing else (decision-0009 item 3)."""

    allow: tuple[Destination, ...] = ()


@dataclass(frozen=True)
class EmptyHost:
    """A refusal: `destination` names no host."""

    destination: Destination


@dataclass(frozen=True)
class PortOutOfRange:
    """A refusal: `destination`'s port is not a whole number from 1 to 65535. Every grant names
    one port; there are no port wildcards."""

    destination: Destination


@dataclass(frozen=True)
class MisplacedWildcard:
    """A refusal: `destination`'s host has a `*` anywhere but as a whole leading label (`*.`):
    `*`, `*example.com`, `a.*.example.com` and `*.*.example.com` all mean something a matcher
    would have to guess at."""

    destination: Destination


@dataclass(frozen=True)
class CidrNotation:
    """A refusal: `destination`'s host is an address range (`10.0.0.0/8`). A grant names one
    address; an embedder that means several grants each."""

    destination: Destination


@dataclass(frozen=True)
class InvalidHostname:
    """A refusal: `destination`'s host is neither an IP literal nor a valid hostname: labels of 1
    to 63 ASCII letters, digits and hyphens, no hyphen at either end, 253 characters at most, and a
    last label that is not a number (`10.1`, `0x7f`), which a resolver would read as an IPv4
    address. An internationalised name is written in its `xn--` form. An IPv6 literal with a zone
    (`fe80::1%eth0`) is refused here too: a grant names an address, not an interface."""

    destination: Destination


@dataclass(frozen=True)
class NeedlessBrackets:
    """A refusal: `destination`'s host is bracketed (`[::1]`). Brackets keep an IPv6 literal apart
    from its port in an authority; a `Destination` holds the port apart already, so it names the
    address bare."""

    destination: Destination


type DestinationRefusal = (
    EmptyHost
    | PortOutOfRange
    | MisplacedWildcard
    | CidrNotation
    | InvalidHostname
    | NeedlessBrackets
)
"""Why one `Destination` cannot be granted."""


@dataclass(frozen=True)
class Authority:
    """What a request asks to reach: `host` (a hostname or an IP literal, unbracketed) and `port`.
    From an HTTP `CONNECT` or an absolute URL by `parse_authority`; from a SOCKS5 request built
    directly, its name or its literal's text and its port."""

    host: str
    port: int


class AuthorityProblem(StrEnum):
    """What made a request's authority unreadable."""

    EMPTY = "empty"
    UNCLOSED_BRACKET = "unclosed-bracket"
    AFTER_BRACKET = "after-bracket"
    BRACKETED_NOT_IPV6 = "bracketed-not-ipv6"
    BARE_IPV6 = "bare-ipv6"
    NO_PORT = "no-port"
    BAD_PORT = "bad-port"
    BAD_HOST = "bad-host"


@dataclass(frozen=True)
class AuthorityUnparseable:
    """A refusal: `text`, the authority a request named (or, for an `Authority` built directly,
    its host or port), cannot be read as one host and one port, for the reason `problem`. An
    authority the parser cannot read is one no grant can be trusted to have matched."""

    text: str
    problem: AuthorityProblem


@dataclass(frozen=True)
class Allowed:
    """The request may go: `grant` is the entry that allows it, and `addresses` what to connect
    to, in the order resolved: the literal itself, or every address the name resolved to, each
    already judged. The caller connects to these and to nothing it resolves again."""

    grant: Destination
    addresses: tuple[str, ...]


@dataclass(frozen=True)
class Resolve:
    """Not decided yet: a name grant matches `name` (lower-case, no trailing dot). Resolve it and
    call `decide_egress` again with the addresses it resolved to."""

    name: str


@dataclass(frozen=True)
class NotGranted:
    """A refusal: no grant names `authority`'s host with its port."""

    authority: Authority


@dataclass(frozen=True)
class Unresolved:
    """A refusal: `authority`'s host is granted, but it resolved to no address."""

    authority: Authority


@dataclass(frozen=True)
class AddressUnparseable:
    """A refusal: `authority`'s host resolved to `address`, which is not an IP address."""

    authority: Authority
    address: str


@dataclass(frozen=True)
class PrivateAddress:
    """A refusal: `authority`'s host is granted by name, but resolved to `address`, which is not
    public (loopback, link-local, private, unique-local, unspecified, reserved, multicast or one
    of the host's own addresses), and no IP-literal grant names it with the same port. One such
    address refuses the request, whatever else the name resolved to."""

    authority: Authority
    address: str


@dataclass(frozen=True)
class _Name:
    """A grant's exact hostname, lower-case and with no trailing dot."""

    name: str


@dataclass(frozen=True)
class _Under:
    """A grant's `*.suffix`: the suffix, lower-case and with no trailing dot."""

    suffix: str


_LABEL_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")

_NAT64 = IPv6Network("64:ff9b::/96")
"""The well-known NAT64 prefix (RFC 6052): the address it carries is the IPv4 one in its last 32
bits, judged as that address."""


def _unmapped(address: _Address) -> _Address:
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _literal(host: str) -> _Address | None:
    """`host` as an IP literal (bare, no zone), IPv4-mapped read as IPv4; else `None`."""
    if "%" in host:
        return None
    try:
        return _unmapped(ip_address(host))
    except ValueError:
        return None


def _label_valid(label: str) -> bool:
    return (
        0 < len(label) <= 63
        and set(label) <= _LABEL_CHARACTERS
        and not label.startswith("-")
        and not label.endswith("-")
    )


def _numeric(label: str) -> bool:
    """Whether a resolver could read `label`, as a name's last, as part of an IPv4 address:
    decimal or octal digits, or `0x` and hex digits (inet_aton's forms)."""
    if label.isdigit():
        return True
    return label.startswith("0x") and all(character in hexdigits for character in label[2:])


def _name(host: str) -> str | None:
    """`host` as a valid hostname, lower-case and with one trailing dot dropped; else `None`."""
    name = host.lower().removesuffix(".")
    if not name or len(name) > 253:
        return None
    labels = name.split(".")
    if not all(_label_valid(label) for label in labels) or _numeric(labels[-1]):
        return None
    return name


def _range(host: str) -> bool:
    try:
        ip_network(host, strict=False)
    except ValueError:
        return False
    return True


def _form(host: str) -> _Address | _Name | _Under | None:
    """What a grant's `host` matches, or `None` for a host no request can match."""
    if host.startswith("*."):
        suffix = _name(host[2:])
        return None if suffix is None else _Under(suffix)
    address = _literal(host)
    if address is not None:
        return address
    name = _name(host)
    return None if name is None else _Name(name)


def _port_valid(port: int) -> bool:
    return type(port) is int and 1 <= port <= 65535


def _destination_refusal(destination: Destination) -> DestinationRefusal | None:
    host = destination.host
    if not host:
        return EmptyHost(destination)
    if host.startswith("[") and host.endswith("]"):
        return NeedlessBrackets(destination)
    if "/" in host and _range(host):
        return CidrNotation(destination)
    if "*" in host and not (host.startswith("*.") and "*" not in host[2:]):
        return MisplacedWildcard(destination)
    if _form(host) is None:
        return InvalidHostname(destination)
    if not _port_valid(destination.port):
        return PortOutOfRange(destination)
    return None


def egress_refusal(policy: EgressPolicy) -> DestinationRefusal | None:
    """Why `policy` cannot be granted, or `None`: the first entry, in `allow`'s order, with an
    empty host, a bracketed host, an address range, a misplaced wildcard, a host that is no valid
    hostname or IP literal, or a port outside 1 to 65535."""
    for destination in policy.allow:
        refused = _destination_refusal(destination)
        if refused is not None:
            return refused
    return None


def _requested(host: str) -> _Address | str | None:
    """A request's `host` as the literal it names, else the valid hostname (lower-case, no
    trailing dot), else `None`."""
    literal = _literal(host)
    return literal if literal is not None else _name(host)


def _port(text: str) -> int | None:
    if not (text.isascii() and text.isdigit() and len(text) <= 5):
        return None
    port = int(text)
    return port if 1 <= port <= 65535 else None


def _split(text: str) -> tuple[str, str | None] | AuthorityProblem:
    """`text` as its host and its port's text (`None` when it names none), brackets removed."""
    if not text:
        return AuthorityProblem.EMPTY
    if text.startswith("["):
        close = text.find("]")
        if close == -1:
            return AuthorityProblem.UNCLOSED_BRACKET
        host, rest = text[1:close], text[close + 1 :]
        if _literal(host) is None or ":" not in host:
            return AuthorityProblem.BRACKETED_NOT_IPV6
        if not rest:
            return host, None
        if not rest.startswith(":"):
            return AuthorityProblem.AFTER_BRACKET
        return host, rest[1:]
    match text.count(":"):
        case 0:
            return text, None
        case 1:
            host, _, port = text.partition(":")
            return host, port
        case _:
            return AuthorityProblem.BARE_IPV6


def parse_authority(text: str, default_port: int | None = None) -> Authority | AuthorityUnparseable:
    """`text` (`host:port`, `[v6]:port`, or with no port when `default_port` is given: an
    absolute URL's `http://host/`) as the `Authority` it names, or why it cannot be read. An
    HTTP `CONNECT` passes no `default_port`, since its authority always names one. Nothing is
    guessed: whitespace, an empty port, a zone (`[fe80::1%25eth0]`) or a bare IPv6 literal is
    refused, never trimmed or reinterpreted."""
    split = _split(text)
    if isinstance(split, AuthorityProblem):
        return AuthorityUnparseable(text, split)
    host, port_text = split
    if _requested(host) is None:
        return AuthorityUnparseable(text, AuthorityProblem.BAD_HOST)
    if port_text is None:
        if default_port is None:
            return AuthorityUnparseable(text, AuthorityProblem.NO_PORT)
        port: int | None = default_port if _port_valid(default_port) else None
    else:
        port = _port(port_text)
    if port is None:
        return AuthorityUnparseable(text, AuthorityProblem.BAD_PORT)
    return Authority(host, port)


def _public(address: _Address, own: frozenset[_Address]) -> bool:
    """Whether a name may reach `address` with no IP-literal grant naming it: globally reachable,
    not reserved or multicast, not a deprecated site-local IPv6 address, and none of the host's
    own; a NAT64 address is judged as the IPv4 address it carries."""
    if isinstance(address, IPv6Address) and address in _NAT64:
        return _public(IPv4Address(int(address) & 0xFFFFFFFF), own)
    if address in own:
        return False
    if isinstance(address, IPv6Address) and address.is_site_local:
        return False
    return address.is_global and not address.is_reserved and not address.is_multicast


def _resolved_address(text: str) -> _Address | None:
    """`text`, an address a lookup returned, IPv4-mapped read as IPv4; a zone (`fe80::1%eth0`) is
    kept, so the address is judged and never equals a grant's, which names none. Else `None`."""
    try:
        return _unmapped(ip_address(text))
    except ValueError:
        return None


def decide_egress(
    policy: EgressPolicy,
    request: Authority,
    resolved: tuple[str, ...] | None = None,
    host_addresses: tuple[str, ...] = (),
) -> (
    Allowed
    | Resolve
    | NotGranted
    | Unresolved
    | AddressUnparseable
    | PrivateAddress
    | AuthorityUnparseable
):
    """Whether `request` may go under `policy`.

    An IP-literal request is allowed only by a literal grant of that address and port, and never
    by a name grant, whatever the name resolves to. A name request is matched against the exact
    and `*.suffix` grants with its port; with none, it is `NotGranted` and never resolved. With
    one and no `resolved`, the answer is `Resolve`. With `resolved` (what the name resolved to,
    as address text), it is allowed only if every address is public or named, with the request's
    port, by an IP-literal grant; `host_addresses` are the host's own, never public. A grant
    `egress_refusal` would refuse matches nothing.

    Returns `AuthorityUnparseable` for a request whose host is no valid hostname or literal, or
    whose port is outside 1 to 65535 (a SOCKS5 request, built directly, may carry either).
    """
    if not _port_valid(request.port):
        return AuthorityUnparseable(str(request.port), AuthorityProblem.BAD_PORT)
    grants = tuple(
        (grant, _form(grant.host))
        for grant in policy.allow
        if _port_valid(grant.port) and grant.port == request.port
    )
    match _requested(request.host):
        case None:
            return AuthorityUnparseable(request.host, AuthorityProblem.BAD_HOST)
        case IPv4Address() | IPv6Address() as literal:
            granted = next((grant for grant, form in grants if form == literal), None)
            return NotGranted(request) if granted is None else Allowed(granted, (str(literal),))
        case str() as name:
            pass
        case _ as unreachable:
            assert_never(unreachable)
    granted = next(
        (
            grant
            for grant, form in grants
            if (isinstance(form, _Name) and form.name == name)
            or (isinstance(form, _Under) and name.endswith(f".{form.suffix}"))
        ),
        None,
    )
    if granted is None:
        return NotGranted(request)
    if resolved is None:
        return Resolve(name)
    if not resolved:
        return Unresolved(request)
    opened = frozenset(form for _, form in grants if isinstance(form, IPv4Address | IPv6Address))
    own = frozenset(
        address for address in map(_resolved_address, host_addresses) if address is not None
    )
    judged = tuple((text, _resolved_address(text)) for text in resolved)
    for text, address in judged:
        if address is None:
            return AddressUnparseable(request, text)
        if not _public(address, own) and address not in opened:
            return PrivateAddress(request, text)
    return Allowed(granted, tuple(str(address) for _, address in judged))
