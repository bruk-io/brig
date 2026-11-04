"""Which environment variables a jail's command may see: the policy and its pure filter, and the
proxy variables a jail with an egress policy sets itself (decision-0009 item 7)."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvPolicy:
    """The complete set of environment variable names a jail's command may see."""

    allowed: tuple[str, ...]


DENY_ALL = EnvPolicy(allowed=())
"""The default: the command sees no environment at all."""


def scrub_env(host_env: Mapping[str, str], policy: EnvPolicy) -> frozendict[str, str]:
    """`host_env` filtered to the names `policy.allowed` lists, in that order. A listed name
    `host_env` does not set is left out, never made up."""
    return frozendict({name: host_env[name] for name in policy.allowed if name in host_env})


PROXY_VARIABLES: tuple[str, ...] = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)
"""The names a jail with an egress policy sets itself (`proxy_environment`), whatever its
`EnvPolicy` says: both cases, since clients disagree on which they read."""


def proxy_environment(port: int) -> frozendict[str, str]:
    """`PROXY_VARIABLES` pointing at the jail's own bridge on `127.0.0.1:<port>`: HTTP and HTTPS
    through it as an HTTP proxy, everything else (`ALL_PROXY`) as SOCKS5 with the name resolved
    by the proxy (`socks5h`), and `NO_PROXY` empty, so no destination is sent around it
    (decision-0009 item 7, old SPEC decision-170)."""
    http = f"http://127.0.0.1:{port}"
    socks = f"socks5h://127.0.0.1:{port}"
    values = {"HTTP_PROXY": http, "HTTPS_PROXY": http, "ALL_PROXY": socks, "NO_PROXY": ""}
    return frozendict({name: values[name.upper()] for name in PROXY_VARIABLES})


@dataclass(frozen=True)
class ProxyVariableNamed:
    """A refusal: `name`, one of `PROXY_VARIABLES`, is in an `EnvPolicy` for a jail with an
    egress policy, which sets it itself."""

    name: str


def proxy_variable_refusal(policy: EnvPolicy) -> ProxyVariableNamed | None:
    """The first name `policy` allows that a jail with an egress policy sets itself, or `None`:
    such a name is refused rather than silently overridden (decision-0009 item 7)."""
    named = next((name for name in policy.allowed if name in PROXY_VARIABLES), None)
    return None if named is None else ProxyVariableNamed(named)
