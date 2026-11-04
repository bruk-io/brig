"""The bwrap jail type's presentation (decision-0001 rule 3, decision-0007 item 5): writing the
supervisor script, refusing and compiling the policy, starting the jail through the shared driver,
and holding the jail's PID namespace for channel readiness. With an egress policy, the jail's one
route out: the supervisor's loopback bridge to a per-jail proxy on the host (decision-0009 items
1, 2 and 7)."""

import os
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import assert_never

from brig.domain import operations
from brig.domain.channels import (
    Reservations,
)
from brig.domain.effects import GroupState, Process
from brig.domain.jail_types import bwrap
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
from brig.infra import state_dir as _state_dir_mod
from brig.infra.proxy import assemble as _proxy_assemble
from brig.infra.proxy import launch as _proxy_launch
from brig.infra.supervisor import assemble, link
from brig.presentation.api import EgressLimits, check_egress_limits, check_egress_policy
from brig.presentation.driver import run
from brig.presentation.errors import (
    ChannelDirectoryCreateFailed,
    ChannelNamespaceNotFound,
    EgressProxySourceUnreadable,
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
    PLACEHOLDERS,
    PROCESSES,
    Jail,
    dismantle,
    real_egress_port,
    real_supervisor_port,
    resolved_state_dir,
)
from brig.presentation.ports import (
    ChannelDirectoryPort,
    EgressPort,
    PlaceholderPort,
    ProcessPort,
    SupervisorPort,
)


def _supervisor_path(state_dir: str) -> tuple[str, ...]:
    """Write the assembled supervisor (`infra.supervisor.assemble`) to a fresh file in brig's
    state directory, `state_dir`, and return the argv that runs it. A new file per jail, so
    `destroy_jail` deletes only its own (TASK-0001.21); the compile binds it back inside the
    state directory's mask, so any policy reaches it (TASK-0019).

    `-I` keeps `PYTHONPATH`, `PYTHONHOME` and user site-packages out of the supervisor, beside
    `link.py` giving it no environment of the caller's; it does nothing for `LD_PRELOAD`, which
    only the environment split keeps out.

    The source is read before the file is made, outside the write's error handling, so a broken
    install is never reported as a state directory the host refused (TASK-0047).

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


def _bridge(
    egress: EgressPolicy, hosts: Mapping[str, tuple[str, ...]] | None, limits: EgressLimits
) -> link.Bridge:
    """The jail's egress route: the supervisor's port on the jail's loopback, and the proxy that
    decides with `egress`, its program assembled with the decision's own source inlined
    (`infra.proxy.assemble`), run from its stdin under `-I` by this interpreter. `hosts`, when
    given, is the table the proxy resolves names from instead of the host's resolver; `limits`
    are what the route may hold, each carried on the line its program reads.

    Raises:
        EgressProxySourceUnreadable: brig's own proxy or decision source could not be read;
            nothing was written or started.
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
    return link.Bridge(port=bwrap.EGRESS_BRIDGE_PORT, proxy=launch, limit=limits.bridge_connections)


def _facts(paths: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    """`infra.files.facts` of each of `paths`, one at a time so a refusal names its own path.

    Raises:
        PolicyPathUninspectable: the host refused to say what is at a path (a directory on the
            way the embedder's user cannot search, a symbolic link loop); the `OSError` is the
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
) -> tuple[SupervisorPort, EgressPort | None, Path, tuple[bwrap.Mount, ...], tuple[str, ...]]:
    """Refuse or compile `policy` for one jail, and return its `SupervisorPort` (a fresh
    `LiveSupervisor`), the supervisor script written for it, its mounts, and the absent paths
    it holds placeholders for; with `bridge`, the supervisor bridges the jail to its egress proxy,
    and the `EgressPort` to that proxy comes second (`None` without).
    Nothing is written before every refusal has passed. Beside what is
    listed below, `PolicyPathUninspectable` from `_facts` and `_link_chain` (the host refused to
    say what is at a policy path, a stdio path or the interpreter, or where a link on the way to
    one leads) and `SupervisorSourceUnreadable` from `_supervisor_path` (brig's own supervisor
    source could not be read) propagate (TASK-0047).

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
        PolicyInterpreterUnreachable: the policy does not mount the interpreter the supervisor
            runs under, or a link on the way to it.
        StateDirectoryWriteFailed: the host refused to make the state directory or its empty
            directory, or to write the supervisor script (TASK-0046).
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
    kinds = {path: found.kind for path, found in host.items()}
    for path, (kind, _) in _facts(bwrap.pin_candidates(policy)).items():
        kinds.setdefault(path, PathKind(kind))
    try:
        empty_dir = str(_state_dir_mod.ensure_empty(Path(state_dir)))
    except OSError as error:
        raise StateDirectoryWriteFailed(f"{state_dir}/empty") from error
    supervisor_path = _supervisor_path(state_dir)
    mounts = bwrap.compile_mounts(
        policy,
        kinds,
        state_dir=state_dir,
        supervisor_script=supervisor_path[-1],
        empty_dir=empty_dir,
        channels=channels,
    )
    supervisor_argv = bwrap.compile_supervisor_launch(supervisor_path, mounts, cwd)
    live = link.LiveSupervisor(supervisor_argv, streams, bridge)
    port = real_supervisor_port(live)
    egress_port = None if bridge is None else real_egress_port(live)
    held = (*policy.write_denies, *policy.masks)
    placeholders = tuple(
        dict.fromkeys(
            mount.target
            for mount in mounts
            if mount.kind is bwrap.MountKind.READ_ONLY and mount.target in held
        )
    )
    return port, egress_port, Path(supervisor_path[-1]), mounts, placeholders


def create_bwrap_jail(
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
) -> Jail:
    """Compile `command` into a bwrap jail and start its supervisor running it.

    Args:
        command: The command, with each channel's endpoint already in its argv.
        env: The candidate environment; `env_policy` decides what of it the command sees
            (default `DENY_ALL`: nothing).
        policy: What the command may see of the host's filesystem (default: all of it,
            read-only).
        env_policy: The environment allow-list.
        channels: What `reserve_channels` returned for this jail. Its channel directory is
            created here, private to the owning user, and bound writable into the jail; it is
            never put in `env` (old SPEC decision-184/186). An fd on it is opened as soon as it
            is made and held on the `Jail` for readiness to open each channel's name beneath
            (TASK-0045).
        cwd: The command's working directory, inside a root of `policy`; the embedder's own
            when unset.
        stdio: Where the command's fd 0, 1 and 2 are pumped from and to; the embedder's own by
            default. The command gets pipes, never these (TASK-0042); `destroy_jail` ends the
            pumps.
        egress: What the command may reach off the jail (decision-0009). `None`, the default,
            starts nothing and changes nothing: the jail has loopback only. Given one (an empty
            `allow` included), the jail's supervisor listens on `127.0.0.1:3128` in the jail
            and bridges each connection to a proxy on the host that allows only what `egress`
            grants; the command's `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` (`socks5h://`) and
            their lower-case forms point there and `NO_PROXY`/`no_proxy` are empty, whatever
            `env_policy` says. `destroy_jail` ends the proxy. While the command runs,
            `allow_egress` and `revoke_egress` change what the proxy grants, and
            `egress_decisions` reads what it decided; the report's `network` claim is then
            `NETWORK_EGRESS_CLAIM`.
        egress_hosts: With `egress`, a table the proxy resolves names from instead of the
            host's resolver (a name it lacks resolves to nothing): host data given as data,
            for a test or an embedder that pins its names. Every address is still judged
            (decision-0009 item 4). Unused without `egress`.
        egress_limits: With `egress`, how much of the host its route may hold (TASK-0049):
            each limit at its default unless lowered, which a test does so a limit is reached
            in seconds. Carried on the host's own line to each program, never the jail's.
            Unused without `egress`.
        processes: The `ProcessPort` (a fake in a test).
        supervisors: A `SupervisorPort` to use as given (a fake in a test); `policy` is then not
            compiled, no supervisor script is written and no egress proxy started (`egress` is
            still refused if malformed, and still sets the proxy variables), so the `Jail` has
            no egress port.
        directories: The `ChannelDirectoryPort`.
        placeholders: The `PlaceholderPort` that holds the directories the jail mounts over at
            absent paths (a fake in a test).
        proc_root: Where to scan for the jail's PID 1; `/proc` except in a test.

    A failure cleans up through `dismantle`, the cleanup `destroy_jail` runs (TASK-0044), before
    the exception propagates. Once the supervisor has been spawned, that is the verified kill
    ladder first, and the placeholders are released only if it reports the group gone; a
    supervisor port whose start spawned the supervisor and then failed hands it back on its
    `JailSpawnFailed`, so it is torn down the same way (TASK-0046). Before the spawn there is no
    process, and everything made (the script, the channel directory, the placeholders) is
    removed (TASK-0012). The cleanup never hides the step's error: what its kill ladder or the
    supervisor's close raised is added to that error as a note (TASK-0046). Beside what is
    listed below, the policy refusals of `_supervisors_for`, `StateDirectoryInvalid`,
    `StateDirectoryWriteFailed` (the host refused to make brig's state directory or its empty
    directory, or to write the supervisor script, before anything started; TASK-0046),
    `PolicyPathUninspectable` (the host refused to say what is at a path the policy or stdio
    names, or at the interpreter; TASK-0047), `SupervisorSourceUnreadable` and
    `EgressProxySourceUnreadable` (brig's own install is broken; TASK-0047), the egress policy
    refusals of `check_egress_policy` and `check_egress_limits`'s `PolicyEgressLimitOutOfRange`,
    before anything else is looked at, and
    `ChannelNamespaceNotFound` from `_namespace_fd_for` propagate. A jail whose command finished
    before its namespace was found has no namespace fd (TASK-0001.30).

    Raises:
        PolicyEnvNamesProxyVariable: with `egress`, `env_policy` allows a proxy variable the
            jail sets itself (decision-0009 item 7); nothing was looked at or started.
        JailSpawnFailed: the driver could not start the supervisor, or its egress proxy (an
            unopenable stdio path included, TASK-0028); a supervisor it spawned before the
            start failed was torn down first (TASK-0046), and a proxy ended.
        ChannelDirectoryCreateFailed: the host refused to create the channel
            directory, or to open it once made.
        PlaceholdersFailed: the host refused a directory for an absent write deny or mask, or
            brig's record of it (TASK-0027), before the start or once it had started.
        JailTeardownFailed: a step failed once the supervisor had been spawned, and the
            teardown that followed still found its group alive, or itself raised so the group
            was never verified gone; the step's own exception is the `__cause__`.
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
    if supervisors is not None:
        resolved_supervisors: SupervisorPort = supervisors
        egress_port: EgressPort | None = None
        supervisor_script: Path | None = None
        mounts: tuple[bwrap.Mount, ...] = ()
        absent: tuple[str, ...] = ()
    else:
        bridge = None if egress is None else _bridge(egress, egress_hosts, egress_limits)
        resolved_supervisors, egress_port, supervisor_script, mounts, absent = _supervisors_for(
            policy, channels, cwd, stdio, bridge
        )
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
        plan = bwrap.compile_run(
            command,
            env=env,
            egress_port=None if egress is None else bwrap.EGRESS_BRIDGE_PORT,
        )
        try:
            process = run(operations.create(plan, env_policy), processes, resolved_supervisors)
        except JailSpawnFailed as error:
            process = error.process  # spawned before the start failed: torn down below
            raise
        if record is not None:
            try:
                placeholders.attach(record, process.pid)
            except OSError as error:
                raise PlaceholdersFailed(absent) from error
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
        )
        if dismantled.ladder_error is not None:
            error.add_note(f"tearing the jail down after this raised {dismantled.ladder_error!r}")
        if dismantled.close_error is not None:
            error.add_note(f"closing the supervisor's pipe raised {dismantled.close_error!r}")
        if process is not None and dismantled.state is not GroupState.GONE:
            raise JailTeardownFailed(process) from error
        raise
    return Jail(
        process=process,
        supervisors=resolved_supervisors,
        supervisor_script=supervisor_script,
        channel_directory=created,
        channel_namespace_fd=namespace_fd,
        channel_directory_fd=directory_fd,
        mounts=mounts,
        placeholders=record,
        report=(
            bwrap.ceilings(
                policy, mounts, channels, _socket_directories(), egress=egress is not None
            )
            if mounts
            else frozendict()
        ),
        egress=egress_port,
    )


def _socket_directories() -> tuple[str, ...]:
    """brig's known socket directories, plus this embedder's runtime directory if it has one."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    extra = (runtime,) if runtime.startswith("/") else ()
    return (*bwrap.SOCKET_DIRECTORIES, *extra)


def _namespace_fd_for(process: Process, proc_root: str = "/proc") -> int | None:
    """An open fd on the jail's PID namespace, found under `process` (the outer bwrap), or
    `None` when the jail's command had already finished and taken the namespace with it
    (TASK-0001.30). Presentation sets the deadline; infra waits.

    Raises:
        ChannelNamespaceNotFound: no in-jail PID 1 appeared before
            `infra.sockets.JAIL_PID1_TIMEOUT_S` passed, with `process` still running, or
            `proc_root` could not be listed (the `OSError` is the `__cause__`).
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
