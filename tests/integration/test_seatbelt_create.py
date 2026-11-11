"""Integration tests for `create_seatbelt_jail`'s refusals and cleanup (decision-0007,
decision-0010): a policy brig cannot compile fails with brig's own error before the channel
directory, the supervisor script or its SBPL profile is written, and whatever was written is
gone again once a create fails or a jail is destroyed.

These go through the real default `supervisors`/`processes` up to the step a fake refuses, so
`_supervisors_for` (where the refusal and the compile run) executes against brig's real state
directory; nothing here starts `sandbox-exec`, so they run on every host.
"""

import dataclasses
from pathlib import Path

import pytest
from tests.integration.fakes import FakeChannelDirectories, FakeProcesses, FakeSupervisors

from brig import (
    WHOLE_HOST_READ_ONLY,
    Channel,
    ChannelDirectoryCreateFailed,
    Destination,
    EgressPolicy,
    EnvPolicy,
    FsPolicy,
    PolicyEnvNamesProxyVariable,
    PolicyMaskHides,
    PolicyPathNotAbsolute,
    create_seatbelt_jail,
    destroy_jail,
    reserve_channels,
)


def _state_files(directory: Path) -> set[str]:
    return {path.name for path in directory.glob("brig-supervisor-*")}


def test_a_mask_hiding_the_channel_directory_is_refused_before_anything_is_created() -> None:
    directories = FakeChannelDirectories(path="/fake/state/channels/0001")
    reserved = reserve_channels((Channel("ctl"),), directories=directories)
    policy = FsPolicy(readable=("/",), masks=("/fake",))

    with pytest.raises(PolicyMaskHides) as exc_info:
        create_seatbelt_jail(("true",), policy=policy, channels=reserved, directories=directories)

    assert (exc_info.value.mask, exc_info.value.path) == ("/fake", "/fake/state/channels/0001")
    assert directories.created == []


def test_a_relative_path_is_refused_before_anything_is_created() -> None:
    directories = FakeChannelDirectories(path="/fake/state/channels/0002")
    reserved = reserve_channels((Channel("ctl"),), directories=directories)

    with pytest.raises(PolicyPathNotAbsolute) as exc_info:
        create_seatbelt_jail(
            ("true",),
            policy=FsPolicy(readable=("/",), writable=("work",)),
            channels=reserved,
            directories=directories,
        )

    assert exc_info.value.path == "work"
    assert directories.created == []


def test_an_egress_jail_whose_env_policy_names_a_proxy_variable_is_refused() -> None:
    directories = FakeChannelDirectories()

    with pytest.raises(PolicyEnvNamesProxyVariable):
        create_seatbelt_jail(
            ("true",),
            env_policy=EnvPolicy(allowed=("HTTPS_PROXY",)),
            egress=EgressPolicy(allow=(Destination("example.com", 443),)),
            directories=directories,
        )

    assert directories.created == []


def test_a_create_that_fails_after_compiling_leaves_no_script_or_profile_behind() -> None:
    """Control: `WHOLE_HOST_READ_ONLY` with a channel directory compiles; the fake refuses the
    directory's create, so the script and its profile were written and must be gone again."""
    reserved = reserve_channels((Channel("ctl"),))
    state_dir = Path(reserved.directory.host_path).parent.parent
    directories = FakeChannelDirectories(path=reserved.directory.host_path, fail_create=True)
    before = _state_files(state_dir)

    with pytest.raises(ChannelDirectoryCreateFailed):
        create_seatbelt_jail(
            ("true",), policy=WHOLE_HOST_READ_ONLY, channels=reserved, directories=directories
        )

    assert _state_files(state_dir) == before


def test_destroying_a_jail_deletes_its_profile_with_its_script(tmp_path: Path) -> None:
    script = tmp_path / "brig-supervisor-fake.py"
    profile = tmp_path / "brig-supervisor-fake.sb"
    script.write_text("# stands in for a real supervisor script\n")
    profile.write_text("(version 1)\n")
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    jail = create_seatbelt_jail(("true",), processes=processes, supervisors=supervisors)
    jail = dataclasses.replace(jail, supervisor_script=script)

    destroy_jail(jail, processes=processes, supervisors=supervisors)

    assert not script.exists()
    assert not profile.exists()
