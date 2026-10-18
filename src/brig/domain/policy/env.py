"""Which environment variables a jail's supervised command may see (decision-0001's
layout; TASK-0001.17): plain data and the one pure filter that applies it, nothing
else (rule 2) -- `operations.py`'s `create` is the only caller of `scrub_env`, over
whatever candidate environment a jail type's own compile already put on `Plan.env`
(`domain/plan.py`'s own docstring). Domain does no I/O (rule 2), so nothing here ever
reads `os.environ` itself; the host's own values arrive already as plain data, on
`Plan.env`, however presentation's own driver got them.
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvPolicy:
    """Which environment variables a jail's supervised command may see: an
    allow-list by name, naming the complete set `scrub_env` ever lets through --
    the same "complete set, not an addition to an implicit default" reading
    `Plan.inheritable_fds`'s own docstring already gives `Spawn`'s fd policy
    (decision-0001 rule 11), mirrored here for environment variables instead of
    file descriptors.
    """

    allowed: tuple[str, ...]


DENY_ALL = EnvPolicy(allowed=())
"""The default `EnvPolicy`: nothing passed through. The safer default (the same
reasoning `Bind`'s own `writable=False` default gives a filesystem bind,
`domain/policy/paths.py`) until an embedder names its own allow-list -- and exactly
what `Plan.env`'s own docstring already called the honest, stated-rather-than-hidden
gap before this policy existed: a jail's supervised command sees no environment at
all unless something names one.
"""


def scrub_env(host_env: Mapping[str, str], policy: EnvPolicy) -> dict[str, str]:
    """Filter `host_env` down to exactly the names `policy.allowed` lists, each kept
    at `host_env`'s own value for that name.

    A name `policy.allowed` lists that `host_env` never set is simply absent from
    the result, never fabricated -- this is a filter, not a merge. The result's own
    key order follows `policy.allowed`'s order (a `dict` keeps insertion order), so
    two calls with the same two arguments, in the same process or a different one,
    always produce the same mapping, key order included.

    Pure: reads only its two arguments, does no I/O, and never mutates either one --
    the one property both this function's own unit test and decision-0001 rule 2
    (domain does no I/O) depend on.

    Returns a plain `dict`, not a `frozendict` (rule 8's own "frozendict for
    mappings"): no such type exists on this project's own interpreter
    (TASK-0001.15's own measured finding -- Python 3.15, `from frozendict import
    frozendict` raises `ModuleNotFoundError` -- and `pyproject.toml` declares no
    dependency to get one, brig being stdlib-only, rule 17). `operations.create`,
    this function's one caller, converts the result straight into the tuple of
    `(name, value)` pairs `StartSupervisedCommand.env` actually carries, the same
    representation `domain/effects.py`'s own docstring already settled on for the
    same reason.
    """
    return {name: host_env[name] for name in policy.allowed if name in host_env}
