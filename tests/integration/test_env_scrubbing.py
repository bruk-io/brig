"""Integration test for environment scrubbing (TASK-0001.17 AC#2): the whole
journey through brig's public API, with `FakeProcesses`/`FakeSupervisors` wired in
at infra's edge, proving the *scrubbed* environment -- not the candidate host-like
environment a caller handed in -- is what actually reaches the supervisor's own
`start` call.

`create_bwrap_jail`'s `env` parameter stands in for whatever a real caller's own
host environment would be (an embedder's `tuple(os.environ.items())`, say) --
nothing in brig reads `os.environ` itself (rule 2: domain does no I/O), so this
test hands in a host-like candidate directly, exactly as a real caller would.
"""

from tests.integration.fakes import FakeProcesses, FakeSupervisors

from brig import EnvPolicy, create_bwrap_jail, destroy_jail


def test_only_the_allowed_names_reach_the_supervisor_start_call() -> None:
    """A jail created with a host-like `env` and a narrow `EnvPolicy` has its
    supervisor started with exactly the allowed names -- `SECRET_TOKEN` and `HOME`,
    present in the candidate `env`, never reach `FakeSupervisors.start` at all.
    """
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    host_like_env = (
        ("PATH", "/usr/bin"),
        ("HOME", "/home/x"),
        ("SECRET_TOKEN", "shh"),
    )
    policy = EnvPolicy(allowed=("PATH",))

    jail = create_bwrap_jail(
        ("true",),
        env=host_like_env,
        env_policy=policy,
        processes=processes,
        supervisors=supervisors,
    )
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert supervisors.started == [(("true",), (("PATH", "/usr/bin"),))]


def test_deny_all_is_the_default_even_with_a_host_like_env_given() -> None:
    """Naming no `env_policy` of its own, a caller gets `DENY_ALL`: the supervisor
    starts with no environment at all, even though a host-like `env` was handed in
    -- the safer default, not a silent pass-through of whatever `env` carries.
    """
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    host_like_env = (("PATH", "/usr/bin"), ("SECRET_TOKEN", "shh"))

    jail = create_bwrap_jail(
        ("true",), env=host_like_env, processes=processes, supervisors=supervisors
    )
    destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert supervisors.started == [(("true",), ())]
