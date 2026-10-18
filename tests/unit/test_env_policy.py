"""Unit test for `domain/policy/env.py`'s `scrub_env` (TASK-0001.17 AC#2): a pure
filter, tested with plain data, nothing mocked.
"""

from brig.domain.policy.env import DENY_ALL, EnvPolicy, scrub_env


def test_scrub_env_keeps_only_the_allowed_names() -> None:
    """Names `policy.allowed` lists, and only those, survive -- everything else in
    `host_env` (a secret, an unrelated variable) is dropped.
    """
    host_env = {"PATH": "/usr/bin", "HOME": "/home/x", "SECRET_TOKEN": "shh"}
    policy = EnvPolicy(allowed=("PATH", "HOME"))

    assert scrub_env(host_env, policy) == {"PATH": "/usr/bin", "HOME": "/home/x"}


def test_scrub_env_never_fabricates_a_name_host_env_did_not_set() -> None:
    """A name `policy` allows that `host_env` never set is simply absent from the
    result -- this is a filter, not a merge that invents a default value.
    """
    host_env = {"PATH": "/usr/bin"}
    policy = EnvPolicy(allowed=("PATH", "LANG"))

    assert scrub_env(host_env, policy) == {"PATH": "/usr/bin"}


def test_scrub_env_with_deny_all_always_returns_empty() -> None:
    """`DENY_ALL`, the default policy, lets nothing through regardless of
    `host_env`'s own contents.
    """
    host_env = {"PATH": "/usr/bin", "HOME": "/home/x"}

    assert scrub_env(host_env, DENY_ALL) == {}


def test_scrub_env_is_deterministic_over_the_same_two_arguments() -> None:
    """Calling `scrub_env` twice with the same `host_env`/`policy` produces the same
    result, key order included -- the one property its own caller,
    `operations.create`, and decision-0001 rule 2 (domain does no I/O) depend on.
    """
    host_env = {"PATH": "/usr/bin", "HOME": "/home/x", "LANG": "en_US.UTF-8"}
    policy = EnvPolicy(allowed=("LANG", "PATH"))

    first = scrub_env(host_env, policy)
    second = scrub_env(host_env, policy)

    assert first == second
    assert list(first) == list(second) == ["LANG", "PATH"]


def test_scrub_env_does_not_mutate_either_argument() -> None:
    """Pure: `host_env` and `policy` are unchanged after the call."""
    host_env = {"PATH": "/usr/bin", "SECRET": "shh"}
    policy = EnvPolicy(allowed=("PATH",))

    scrub_env(host_env, policy)

    assert host_env == {"PATH": "/usr/bin", "SECRET": "shh"}
    assert policy == EnvPolicy(allowed=("PATH",))
