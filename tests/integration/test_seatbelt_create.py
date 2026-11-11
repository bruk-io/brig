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
from tests.integration.fakes import (
    FakeChannelDirectories,
    FakeMembers,
    FakeProcesses,
    FakeSupervisors,
)

from brig import (
    WHOLE_HOST_READ_ONLY,
    Channel,
    ChannelDirectoryCreateFailed,
    Destination,
    EgressPolicy,
    EnvPolicy,
    FsPolicy,
    JailMembersUnverifiable,
    JailTeardownFailed,
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


def _member_files(tmp_path: Path) -> tuple[Path, Path]:
    mark = tmp_path / "brig-supervisor-fake.mark"
    decoy = tmp_path / "brig-supervisor-fake.decoy"
    mark.write_text("")
    decoy.write_text("")
    return mark, decoy


def test_destroying_a_jail_kills_what_carries_its_mark_and_then_removes_the_mark(
    tmp_path: Path,
) -> None:
    mark, decoy = _member_files(tmp_path)
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    members = FakeMembers(gone=True)
    jail = create_seatbelt_jail(("true",), processes=processes, supervisors=supervisors)
    jail = dataclasses.replace(jail, member_mark=mark)

    destroy_jail(jail, processes=processes, supervisors=supervisors, members=members)

    assert members.asked == [(str(mark), str(decoy))]
    assert not mark.exists() and not decoy.exists()


def test_a_member_left_alive_fails_teardown_and_keeps_the_mark(tmp_path: Path) -> None:
    """The mark is what finds a process that left the group, so it stays while one may live."""
    mark, decoy = _member_files(tmp_path)
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    members = FakeMembers(gone=False)
    jail = create_seatbelt_jail(("true",), processes=processes, supervisors=supervisors)
    jail = dataclasses.replace(jail, member_mark=mark)

    with pytest.raises(JailTeardownFailed):
        destroy_jail(jail, processes=processes, supervisors=supervisors, members=members)

    assert mark.exists() and decoy.exists()


def test_a_create_that_fails_after_compiling_leaves_no_member_files_behind() -> None:
    reserved = reserve_channels((Channel("ctl"),))
    state_dir = Path(reserved.directory.host_path).parent.parent
    directories = FakeChannelDirectories(path=reserved.directory.host_path, fail_create=True)
    before = {path.name for path in state_dir.iterdir()}

    with pytest.raises(ChannelDirectoryCreateFailed):
        create_seatbelt_jail(
            ("true",), policy=WHOLE_HOST_READ_ONLY, channels=reserved, directories=directories
        )

    assert {path.name for path in state_dir.iterdir()} == before


def test_a_running_supervisor_the_host_does_not_find_fails_teardown(tmp_path: Path) -> None:
    """The canary: `sandbox_check` answering otherwise than measured (as on an architecture
    its call was not measured on) reads every process as no member, so a sweep that found
    nothing would mean nothing. A supervisor known to be running and not found says so."""
    mark, _ = _member_files(tmp_path)
    processes = FakeProcesses()
    supervisors = FakeSupervisors()
    members = FakeMembers(found=False, gone=True)
    jail = create_seatbelt_jail(("true",), processes=processes, supervisors=supervisors)
    jail = dataclasses.replace(jail, member_mark=mark)

    with pytest.raises(JailMembersUnverifiable):
        destroy_jail(jail, processes=processes, supervisors=supervisors, members=members)

    assert members.checked == [(str(mark), str(mark.with_suffix(".decoy")), jail.process.pid)]
    assert mark.exists()


def test_a_supervisor_that_has_exited_tells_the_canary_nothing(tmp_path: Path) -> None:
    mark, _ = _member_files(tmp_path)
    processes = FakeProcesses(leader_exited=True)
    supervisors = FakeSupervisors()
    members = FakeMembers(found=False, gone=True)
    jail = create_seatbelt_jail(("true",), processes=processes, supervisors=supervisors)
    jail = dataclasses.replace(jail, member_mark=mark)

    destroy_jail(jail, processes=processes, supervisors=supervisors, members=members)

    assert members.checked == []


def test_a_member_left_alive_is_named_apart_from_a_live_group(tmp_path: Path) -> None:
    mark, _ = _member_files(tmp_path)
    supervisors = FakeSupervisors()
    left = FakeMembers(gone=False)
    jail = create_seatbelt_jail(("true",), processes=FakeProcesses(), supervisors=supervisors)
    jail = dataclasses.replace(jail, member_mark=mark)

    with pytest.raises(JailTeardownFailed) as members_failed:
        destroy_jail(jail, processes=FakeProcesses(), supervisors=supervisors, members=left)
    group_jail = create_seatbelt_jail(
        ("true",), processes=FakeProcesses(alive=True), supervisors=supervisors
    )
    with pytest.raises(JailTeardownFailed) as group_failed:
        destroy_jail(group_jail, processes=FakeProcesses(alive=True), supervisors=supervisors)

    assert members_failed.value.members_left
    assert "left its process group" in str(members_failed.value)
    assert not group_failed.value.members_left
    assert "process group still alive" in str(group_failed.value)


def test_destroy_sweeps_the_marks_earlier_teardowns_kept(tmp_path: Path) -> None:
    mark, _ = _member_files(tmp_path)
    members = FakeMembers()
    supervisors = FakeSupervisors()
    jail = create_seatbelt_jail(("true",), processes=FakeProcesses(), supervisors=supervisors)
    jail = dataclasses.replace(jail, member_mark=mark)

    destroy_jail(jail, processes=FakeProcesses(), supervisors=supervisors, members=members)

    assert members.reaped == [str(tmp_path)]
