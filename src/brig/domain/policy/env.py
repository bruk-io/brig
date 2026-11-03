"""Which environment variables a jail's command may see: the policy and its pure filter."""

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
