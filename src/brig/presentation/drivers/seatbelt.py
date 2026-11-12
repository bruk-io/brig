"""The Seatbelt jail type's presentation (decision-0001 rule 3, decision-0010): writing the
supervisor script and its SBPL profile, refusing and compiling the policy, starting the jail
through the shared driver under `/usr/bin/sandbox-exec`, and holding the jail's group handle for
channel readiness. With an egress policy, the jail's one route out: the supervisor's loopback
bridge to a per-jail proxy on the host (decision-0009 items 1, 2 and 7; decision-0010 item 4)."""

import os
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import assert_never

from brig.domain import operations
from brig.domain.channels import Reservations
from brig.domain.effects import GroupState, Process
from brig.domain.jail_types import seatbelt
from brig.domain.policy import egress as _egress
from brig.domain.policy.egress import EgressPolicy
from brig.domain.policy.env import (
    DENY_ALL,
    EnvPolicy,
    ProxyVariableNamed,
    proxy_variable_refusal,
)
from brig.domain.policy.paths import (
    WHOLE_HOST_READ_ONLY,
    CwdOutsideRoots,
    FsPolicy,
    HostPath,
    InterpreterUnreachable,
    MaskHides,
    PathKind,
    PathNotAbsolute,
    RootAbsent,
    StdioHardLinked,
    StdioInWritableRoot,
    StdioNotOwnFile,
    StdioThroughLink,
    ThroughLink,
    cwd_refusal,
    interpreter_refusal,
    refusal,
    stdio_refusal,
)
from brig.domain.policy.stdio import INHERIT, Stdio
from brig.infra import files as _files
from brig.infra import sockets as _sockets
from brig.infra.proxy import assemble as _proxy_assemble
from brig.infra.proxy import launch as _proxy_launch
from brig.infra.supervisor import assemble, link
from brig.presentation.api import EgressLimits, check_egress_limits, check_egress_policy
from brig.presentation.driver import run
from brig.presentation.errors import (
    ChannelDirectoryCreateFailed,
    ChannelNamespaceNotFound,
    EgressProxySourceUnreadable,
    JailMembersUnverifiable,
    JailSpawnFailed,
    JailTeardownFailed,
    PlaceholdersFailed,
    PolicyCwdOutsideRoots,
    PolicyEnvNamesProxyVariable,
    PolicyInterpreterUnreachable,
    PolicyMaskHides,
    PolicyPathNotAbsolute,
    PolicyPathThroughLink,
    PolicyPathUninspectable,
    PolicyRootAbsent,
    PolicyStdioHardLinked,
    PolicyStdioInWritableRoot,
    PolicyStdioNotOwnFile,
    PolicyStdioThroughLink,
    StateDirectoryWriteFailed,
    SupervisorSourceUnreadable,
)
from brig.presentation.jail import (
    CHANNEL_DIRECTORIES,
    KILL_GRACE_S,
    MEMBERS,
    PLACEHOLDERS,
    PROCESSES,
    Jail,
    dismantle,
    member_decoy,
    real_egress_port,
    real_supervisor_port,
    resolved_state_dir,
)
from brig.presentation.ports import (
    ChannelDirectoryPort,
    EgressPort,
    MembersPort,
    PlaceholderPort,
    ProcessPort,
    SupervisorPort,
)


def _supervisor_path(state_dir: str) -> tuple[str, ...]:
    """Write the assembled supervisor (`infra.supervisor.assemble`) to a fresh file in brig's
    state directory, `state_dir`, and return the argv that runs it. A new file per jail, so
    `destroy_jail` deletes only its own (TASK-0001.21); the compile allows it inside the state
    directory's mask, so any policy reaches it (TASK-0019).

    Raises:
        SupervisorSourceUnreadable: brig's own supervisor source could not be read; nothing was
            written (TASK-0047).
        StateDirectoryWriteFailed: the host refused the file or its write; a file written in
            part is removed first (TASK-0046).
    """
    try:
        source = assemble.assembled_source()
    except OSError as error:
        raise SupervisorSourceUnreadable() from error
    written: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="brig-supervisor-",
            delete=False,
            dir=state_dir,
        ) as handle:
            written = handle.name
            handle.write(source)
    except OSError as error:
        if written is not None:
            Path(written).unlink(missing_ok=True)
        raise StateDirectoryWriteFailed(state_dir) from error
    return (sys.executable, "-I", handle.name)


def _write_new(path: Path, text: str) -> None:
    """Write `text` to `path`, a new file private to the embedder's user, as the script is.

    Raises:
        OSError: the host refused the file or its write; a file made in part is removed.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        path.unlink(missing_ok=True)
        raise


def _write_member_files(script_path: Path, state_dir: str) -> Path:
    """Make the jail's member mark, `script_path.with_suffix(".mark")`, and its decoy beside it
    (`member_decoy`), both empty: `sandbox_check` answers only for a path that exists, so
    teardown can find the jail's processes by them (`infra.members`). On failure the script and
    whatever was made are removed.

    Raises:
        StateDirectoryWriteFailed: the host refused either file.
    """
    mark = script_path.with_suffix(".mark")
    try:
        _write_new(mark, "")
        _write_new(member_decoy(mark), "")
    except OSError as error:
        mark.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
        raise StateDirectoryWriteFailed(state_dir) from error
    return mark


def _write_profile(script_path: Path, profile_text: str, state_dir: str) -> Path:
    """Write `profile_text` to `script_path.with_suffix(".sb")`, removing it, the script and the
    member files on failure.

    Raises:
        StateDirectoryWriteFailed: the host refused the profile file or its write.
    """
    profile_path = script_path.with_suffix(".sb")
    try:
        _write_new(profile_path, profile_text)
    except OSError as error:
        mark = script_path.with_suffix(".mark")
        for made in (mark, member_decoy(mark), script_path):
            made.unlink(missing_ok=True)
        raise StateDirectoryWriteFailed(state_dir) from error
    return profile_path


def _bridge(
    command: tuple[str, ...],
    egress: EgressPolicy,
    hosts: Mapping[str, tuple[str, ...]] | None,
    limits: EgressLimits,
) -> tuple[link.Bridge, _sockets.BridgeSockets]:
    """The jail's egress route, and the sockets the host holds at its port: a port of its own,
    which the host listens on at `127.0.0.1` and `[::1]` and hands the supervisor, and holds,
    not listening, at every other local address (`infra.sockets.bridge_listeners`,
    decision-0011); and the proxy that
    decides with `egress`, its program assembled with the decision's own source inlined
    (`infra.proxy.assemble`), run from its stdin under `-I` by this interpreter. A port per
    jail, so jails with egress run side by side on the host's one network stack, and the jail
    itself binds nothing (decision-0010 item 4). The caller holds the sockets for the jail's
    life: on the `Jail` once it is made, closed by `dismantle`; closed by the caller itself on a
    failure before that.

    Raises:
        EgressProxySourceUnreadable: brig's own proxy or decision source could not be read;
            nothing was written or started.
        JailSpawnFailed: no port could be bound free on every local address; the `OSError` is
            the `__cause__`, and nothing is left open.
    """
    try:
        decision_source = Path(_egress.__file__).read_text(encoding="utf-8")
        source = _proxy_assemble.assembled_source(decision_source)
    except OSError as error:
        raise EgressProxySourceUnreadable() from error
    table = (
        None
        if hosts is None
        else frozendict({name: tuple(addresses) for name, addresses in hosts.items()})
    )
    launch = _proxy_launch.ProxyLaunch(
        argv=(sys.executable, "-I", "-"),
        source=source,
        allow=tuple((destination.host, destination.port) for destination in egress.allow),
        hosts=table,
        connections=limits.connections,
        handshake_s=limits.handshake_s,
    )
    try:
        held = _sockets.bridge_listeners()
    except OSError as error:
        raise JailSpawnFailed(command) from error
    bridge = link.Bridge(
        port=held.port, proxy=launch, limit=limits.bridge_connections, listeners=held.listeners
    )
    return bridge, held


def _release(held: _sockets.BridgeSockets | None) -> None:
    """Close every socket the host holds at a jail's bridge port; a no-op once closed."""
    if held is not None:
        held.close()


def _facts(paths: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    """`infra.files.facts` of each of `paths`, one at a time so a refusal names its own path.

    Raises:
        PolicyPathUninspectable: the host refused to say what is at a path; the `OSError` is the
            `__cause__` (TASK-0047).
    """
    found: dict[str, tuple[str, str]] = {}
    for path in paths:
        try:
            found |= _files.facts((path,))
        except OSError as error:
            raise PolicyPathUninspectable(path) from error
    return found


def _link_chain(path: str) -> tuple[str, ...]:
    """`infra.files.link_chain` of `path`.

    Raises:
        PolicyPathUninspectable: a link on the way could not be read, or changed while it was
            read; the `OSError` is the `__cause__` (TASK-0047).
    """
    try:
        return _files.link_chain(path)
    except OSError as error:
        raise PolicyPathUninspectable(path) from error


def _supervisors_for(
    policy: FsPolicy,
    channels: Reservations | None,
    cwd: str | None = None,
    stdio: Stdio = INHERIT,
    bridge: link.Bridge | None = None,
) -> tuple[
    SupervisorPort, EgressPort | None, Path, tuple[seatbelt.Rule, ...], tuple[str, ...], Path
]:
    """Refuse or compile `policy` for one Seatbelt jail, and return its `SupervisorPort`, the
    `EgressPort` (`None` without `bridge`), the supervisor script path, its compiled `Rule`s,
    the paths it holds placeholders for, and its member mark (`_write_member_files`). Nothing
    is written before every refusal has passed. Beside what is listed below,
    `PolicyPathUninspectable` from `_facts` and `_link_chain`, `SupervisorSourceUnreadable` from
    `_supervisor_path`, and `StateDirectoryWriteFailed` from `_supervisor_path`,
    `_write_member_files` and `_write_profile` (the host refused the supervisor script, the
    member files or the SBPL profile) propagate.

    Raises:
        PolicyPathNotAbsolute: a path in `policy` is not absolute and normalised.
        PolicyMaskHides: a mask hides a root, the state directory or the channel directory.
        PolicyRootAbsent: a readable or writable root does not exist on the host.
        PolicyPathThroughLink: an entry is reached through a symbolic link inside a writable
            root.
        PolicyCwdOutsideRoots: `cwd` is in no root of the policy.
        PolicyStdioInWritableRoot: a stdio path is inside a writable root.
        PolicyStdioThroughLink: a stdio path goes through a symbolic link.
        PolicyStdioHardLinked: an existing stdio file has another name.
        PolicyStdioNotOwnFile: an existing stdio path is not a regular file the embedder owns.
        PolicyInterpreterUnreachable: the policy does not reach the interpreter the supervisor
            runs under, or a link on the way to it.
    """
    state_dir = resolved_state_dir()
    needed = (
        (state_dir,)
        if channels is None or not channels.reservations
        else (
            state_dir,
            channels.directory.host_path,
        )
    )
    every = (*policy.readable, *policy.writable, *policy.write_denies, *policy.masks)
    host = {
        path: HostPath(PathKind(kind), resolved) for path, (kind, resolved) in _facts(every).items()
    }
    match refusal(policy, needed, host):
        case PathNotAbsolute(path=path):
            raise PolicyPathNotAbsolute(path)
        case MaskHides(mask=mask, path=path):
            raise PolicyMaskHides(mask, path)
        case RootAbsent(path=path):
            raise PolicyRootAbsent(path)
        case ThroughLink(path=path, root=root):
            raise PolicyPathThroughLink(path, root)
        case None:
            pass
        case _ as unreachable:
            assert_never(unreachable)
    if cwd is not None:
        match cwd_refusal(policy, cwd):
            case PathNotAbsolute(path=path):
                raise PolicyPathNotAbsolute(path)
            case CwdOutsideRoots(cwd=outside):
                raise PolicyCwdOutsideRoots(outside)
            case MaskHides(mask=mask, path=path):
                raise PolicyMaskHides(mask, path)
            case None:
                pass
            case _ as unreachable:
                assert_never(unreachable)
    streams = (stdio.stdin, stdio.stdout, stdio.stderr)
    named = tuple(path for path in streams if path is not None and path != "/dev/null")
    chains = {path: _link_chain(path) for path in named}
    counts = {path: _files.link_count(path) for path in named}
    first = {path: _files.first_link(path) for path in named}
    own = {path: _files.own_regular_file(path) for path in named}
    match stdio_refusal(policy, streams, chains, counts, first, own):
        case PathNotAbsolute(path=path):
            raise PolicyPathNotAbsolute(path)
        case StdioInWritableRoot(path=path):
            raise PolicyStdioInWritableRoot(path)
        case StdioThroughLink(path=path, link=through):
            raise PolicyStdioThroughLink(path, through)
        case StdioNotOwnFile(path=path):
            raise PolicyStdioNotOwnFile(path)
        case StdioHardLinked(path=path):
            raise PolicyStdioHardLinked(path)
        case None:
            pass
        case _ as unreachable:
            assert_never(unreachable)
    match interpreter_refusal(policy, _link_chain(sys.executable)):
        case InterpreterUnreachable(path=path):
            raise PolicyInterpreterUnreachable(path)
        case None:
            pass
        case _ as unreachable:
            assert_never(unreachable)
    for path, (kind, resolved) in _facts(
        (*seatbelt.pin_candidates(policy, state_dir), *needed)
    ).items():
        host.setdefault(path, HostPath(PathKind(kind), resolved))
    links = {root: _link_chain(root) for root in (*policy.readable, *policy.writable)}
    supervisor_path = _supervisor_path(state_dir)
    script_file = Path(supervisor_path[-1])
    try:
        for path, (kind, resolved) in _facts((supervisor_path[-1],)).items():
            host[path] = HostPath(PathKind(kind), resolved)
    except BaseException:
        script_file.unlink(missing_ok=True)
        raise
    member_mark = _write_member_files(script_file, state_dir)
    rules = seatbelt.compile_rules(
        policy,
        host,
        state_dir=state_dir,
        supervisor_script=supervisor_path[-1],
        channels=channels,
        egress_port=None if bridge is None else bridge.port,
        links=links,
        member_mark=str(member_mark),
    )
    profile_path = _write_profile(script_file, seatbelt.render_profile(rules), state_dir)
    supervisor_argv = seatbelt.compile_supervisor_launch(supervisor_path, str(profile_path), cwd)
    live = link.LiveSupervisor(supervisor_argv, streams, bridge)
    port = real_supervisor_port(live)
    egress_port = None if bridge is None else real_egress_port(live)
    held = (*policy.write_denies, *policy.masks)
    placeholders = tuple(
        dict.fromkeys(
            rule.source
            for rule in rules
            if rule.kind in (seatbelt.RuleKind.WRITE_DENY, seatbelt.RuleKind.MASK)
            and rule.source in held
        )
    )
    return port, egress_port, script_file, rules, placeholders, member_mark


def create_seatbelt_jail(
    command: tuple[str, ...],
    *,
    env: Mapping[str, str] = frozendict(),
    policy: FsPolicy = WHOLE_HOST_READ_ONLY,
    env_policy: EnvPolicy = DENY_ALL,
    channels: Reservations | None = None,
    cwd: str | None = None,
    stdio: Stdio = INHERIT,
    egress: EgressPolicy | None = None,
    egress_hosts: Mapping[str, tuple[str, ...]] | None = None,
    egress_limits: EgressLimits = EgressLimits(),
    processes: ProcessPort = PROCESSES,
    supervisors: SupervisorPort | None = None,
    directories: ChannelDirectoryPort = CHANNEL_DIRECTORIES,
    placeholders: PlaceholderPort = PLACEHOLDERS,
    proc_root: str = "/proc",
    members: MembersPort = MEMBERS,
) -> Jail:
    """Compile `command` into a Darwin Seatbelt jail and start its supervisor running it.

    Raises:
        PolicyEnvNamesProxyVariable: with `egress`, `env_policy` allows a proxy variable the
            jail sets itself (decision-0009 item 7); nothing was looked at or started.
        JailSpawnFailed: the driver could not start the supervisor, or its egress proxy; a
            supervisor it spawned before the start failed was torn down first (TASK-0046), and
            a proxy ended.
        ChannelDirectoryCreateFailed: the host refused to create the channel directory, or to
            open it once made.
        PlaceholdersFailed: the host refused a directory for an absent write deny or mask, or
            brig's record of it (TASK-0027), before the start or once it had started.
        JailTeardownFailed: a step failed once the supervisor had been spawned, and the
            teardown that followed still found its group alive, or itself raised so the group
            was never verified gone; the step's own exception is the `__cause__`.

    Before compiling, `members` sweeps again what earlier teardowns could not end
    (decision-0010 item 2). Once the supervisor runs, the canary (`_await_members_found`)
    raises `JailMembersUnverifiable` if the host cannot find it carrying the jail's profile;
    the jail is torn down first.
    """
    if egress is not None:
        check_egress_policy(egress)
        check_egress_limits(egress_limits)
        match proxy_variable_refusal(env_policy):
            case ProxyVariableNamed(name=name):
                raise PolicyEnvNamesProxyVariable(name)
            case None:
                pass
            case _ as unreachable:
                assert_never(unreachable)
    bridge: link.Bridge | None = None
    held: _sockets.BridgeSockets | None = None
    if supervisors is not None:
        resolved_supervisors: SupervisorPort = supervisors
        egress_port: EgressPort | None = None
        supervisor_script: Path | None = None
        rules: tuple[seatbelt.Rule, ...] = ()
        absent: tuple[str, ...] = ()
        member_mark: Path | None = None
    else:
        members.reap(resolved_state_dir(), time.monotonic() + KILL_GRACE_S)
        if egress is not None:
            bridge, held = _bridge(command, egress, egress_hosts, egress_limits)
        try:
            (
                resolved_supervisors,
                egress_port,
                supervisor_script,
                rules,
                absent,
                member_mark,
            ) = _supervisors_for(policy, channels, cwd, stdio, bridge)
        except BaseException:
            _release(held)
            raise
    channel_directory = (
        Path(channels.directory.host_path)
        if channels is not None and channels.reservations
        else None
    )
    created: Path | None = None
    directory_fd: int | None = None
    namespace_fd: int | None = None
    record: str | None = None
    process: Process | None = None
    try:
        try:
            record = placeholders.hold(absent)
        except OSError as error:
            raise PlaceholdersFailed(absent) from error
        if channel_directory is not None:
            try:
                directories.create(str(channel_directory))
            except OSError as error:
                raise ChannelDirectoryCreateFailed(str(channel_directory)) from error
            created = channel_directory
            try:
                directory_fd = _sockets.open_directory(str(channel_directory))
            except OSError as error:
                raise ChannelDirectoryCreateFailed(str(channel_directory)) from error
        plan = seatbelt.compile_run(
            command,
            env=env,
            egress_port=_proxy_port(egress, bridge),
        )
        try:
            process = run(operations.create(plan, env_policy), processes, resolved_supervisors)
        except JailSpawnFailed as error:
            process = error.process
            raise
        if record is not None:
            try:
                placeholders.attach(record, process.pid)
            except OSError as error:
                raise PlaceholdersFailed(absent) from error
        if member_mark is not None:
            _await_members_found(process, member_mark, members, processes)
        if channel_directory is not None:
            namespace_fd = _namespace_fd_for(process, proc_root)
    except BaseException as error:
        dismantled = dismantle(
            process,
            supervisors=resolved_supervisors,
            processes=processes,
            directories=directories,
            placeholders=placeholders,
            supervisor_script=supervisor_script,
            channel_directory=created,
            channel_namespace_fd=namespace_fd,
            channel_directory_fd=directory_fd,
            placeholder_record=record,
            member_mark=member_mark,
            members=members,
            bridge_sockets=held,
        )
        if dismantled.ladder_error is not None:
            error.add_note(f"tearing the jail down after this raised {dismantled.ladder_error!r}")
        if dismantled.close_error is not None:
            error.add_note(f"closing the supervisor's pipe raised {dismantled.close_error!r}")
        if process is not None and dismantled.state is not GroupState.GONE:
            raise JailTeardownFailed(process, members_left=dismantled.members_left) from error
        raise
    return Jail(
        process=process,
        supervisors=resolved_supervisors,
        supervisor_script=supervisor_script,
        channel_directory=created,
        channel_namespace_fd=namespace_fd,
        channel_directory_fd=directory_fd,
        rules=rules,
        placeholders=record,
        member_mark=member_mark,
        report=(
            seatbelt.ceilings(rules, channels, egress=egress is not None) if rules else frozendict()
        ),
        egress=egress_port,
        bridge_sockets=held,
    )


_MEMBERS_FOUND_TIMEOUT_S = 5.0
"""How long `_await_members_found` waits for the supervisor's profile to read as applied:
`sandbox-exec` applies it before it execs the supervisor, so a running supervisor is found at
once (measured), and this only bounds a slow host."""


def _await_members_found(
    process: Process, mark: Path, members: MembersPort, processes: ProcessPort
) -> None:
    """Wait until the canary finds the jail's supervisor carrying its profile,
    or the supervisor has exited, which tells nothing (a fast command ends it).

    Raises:
        JailMembersUnverifiable: the supervisor ran throughout and was not found before
            `_MEMBERS_FOUND_TIMEOUT_S` passed: teardown could not find the jail's processes on
            this host.
    """
    deadline = time.monotonic() + _MEMBERS_FOUND_TIMEOUT_S
    while True:
        if processes.peek(process.pid) is not None:
            return
        if members.includes(str(mark), str(member_decoy(mark)), process.pid):
            return
        if time.monotonic() >= deadline:
            if processes.peek(process.pid) is not None:
                return
            raise JailMembersUnverifiable(process)
        time.sleep(0.01)


_NO_BRIDGE_PORT = 0
"""The port the proxy variables name for a jail with egress started through a caller's own
`supervisors`, which starts no bridge: one nothing listens on."""


def _proxy_port(egress: EgressPolicy | None, bridge: link.Bridge | None) -> int | None:
    """The port the command's proxy variables name: its bridge's, `None` without egress."""
    if egress is None:
        return None
    return _NO_BRIDGE_PORT if bridge is None else bridge.port


def _namespace_fd_for(process: Process, proc_root: str = "/proc") -> int | None:
    """An open fd holding the jail's identity for channel readiness, or `None` when the jail's
    command had already finished (TASK-0001.30).

    Raises:
        ChannelNamespaceNotFound: no in-jail process appeared before
            `infra.sockets.JAIL_PID1_TIMEOUT_S` passed, with `process` still running, or
            the handle could not be opened (the `OSError` is the `__cause__`).
    """
    try:
        outcome = _sockets.jail_pid1_namespace(
            process.pid, time.monotonic() + _sockets.JAIL_PID1_TIMEOUT_S, proc_root
        )
    except OSError as error:
        raise ChannelNamespaceNotFound(process.pid) from error
    if isinstance(outcome, _sockets.JailPid1NotFound):
        raise ChannelNamespaceNotFound(process.pid)
    if isinstance(outcome, _sockets.JailPid1Exited):
        return None
    return outcome
