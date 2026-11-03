"""The bwrap jail type's presentation (decision-0001 rule 3, decision-0007 item 5): writing the
supervisor script, refusing and compiling the policy, starting the jail through the shared driver,
and holding the jail's PID namespace for channel readiness."""

import os
import secrets
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
from brig.domain.effects import Process
from brig.domain.jail_types import bwrap
from brig.domain.policy.env import DENY_ALL, EnvPolicy
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
from brig.infra import placeholders as _placeholders
from brig.infra import sockets as _sockets
from brig.infra import state_dir as _state_dir_mod
from brig.infra.supervisor import assemble, link
from brig.presentation.driver import run
from brig.presentation.errors import (
    ChannelDirectoryCreateFailed,
    ChannelNamespaceNotFound,
    PlaceholdersFailed,
    PolicyCwdOutsideRoots,
    PolicyInterpreterUnreachable,
    PolicyMaskHides,
    PolicyPathNotAbsolute,
    PolicyPathThroughLink,
    PolicyRootAbsent,
    PolicyStdioHardLinked,
    PolicyStdioInWritableRoot,
    PolicyStdioNotOwnFile,
    PolicyStdioThroughLink,
)
from brig.presentation.jail import (
    CHANNEL_DIRECTORIES,
    PROCESSES,
    Jail,
    close_namespace_fd,
    real_supervisor_port,
    resolved_state_dir,
)
from brig.presentation.ports import (
    ChannelDirectoryPort,
    ProcessPort,
    SupervisorPort,
)


def _supervisor_path() -> tuple[str, ...]:
    """Write the assembled supervisor (`infra.supervisor.assemble`) to a fresh file in brig's
    state directory and return the argv that runs it. A new file per jail, so `destroy_jail`
    deletes only its own (TASK-0001.21); the compile binds it back inside the state directory's
    mask, so any policy reaches it (TASK-0019).

    `-I` keeps `PYTHONPATH`, `PYTHONHOME` and user site-packages out of the supervisor, beside
    `link.py` giving it no environment of the caller's; it does nothing for `LD_PRELOAD`, which
    only the environment split keeps out.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        prefix="brig-supervisor-",
        delete=False,
        dir=resolved_state_dir(),
    ) as handle:
        handle.write(assemble.assembled_source())
    return (sys.executable, "-I", handle.name)


def _supervisors_for(
    policy: FsPolicy,
    channels: Reservations | None,
    cwd: str | None = None,
    stdio: Stdio = INHERIT,
) -> tuple[SupervisorPort, Path, tuple[bwrap.Mount, ...], tuple[str, ...]]:
    """Refuse or compile `policy` for one jail, and return its `SupervisorPort` (a fresh
    `LiveSupervisor`), the supervisor script written for it, its mounts, and the absent paths
    it holds placeholders for. Nothing is written before every refusal has passed.

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
        path: HostPath(PathKind(kind), resolved)
        for path, (kind, resolved) in _files.facts(every).items()
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
    chains = {path: _files.link_chain(path) for path in named}
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
    match interpreter_refusal(policy, _files.link_chain(sys.executable)):
        case InterpreterUnreachable(path=path):
            raise PolicyInterpreterUnreachable(path)
        case None:
            pass
        case _ as unreachable:
            assert_never(unreachable)
    kinds = {path: found.kind for path, found in host.items()}
    empty_dir = str(_state_dir_mod.ensure_empty(Path(state_dir)))
    supervisor_path = _supervisor_path()
    mounts = bwrap.compile_mounts(
        policy,
        kinds,
        state_dir=state_dir,
        supervisor_script=supervisor_path[-1],
        empty_dir=empty_dir,
        channels=channels,
    )
    supervisor_argv = bwrap.compile_supervisor_launch(supervisor_path, mounts, cwd)
    port = real_supervisor_port(link.LiveSupervisor(supervisor_argv, streams))
    held = (*policy.write_denies, *policy.masks)
    placeholders = tuple(
        dict.fromkeys(
            mount.target
            for mount in mounts
            if mount.kind is bwrap.MountKind.READ_ONLY and mount.target in held
        )
    )
    return port, Path(supervisor_path[-1]), mounts, placeholders


def create_bwrap_jail(
    command: tuple[str, ...],
    *,
    env: Mapping[str, str] = frozendict(),
    policy: FsPolicy = WHOLE_HOST_READ_ONLY,
    env_policy: EnvPolicy = DENY_ALL,
    channels: Reservations | None = None,
    cwd: str | None = None,
    stdio: Stdio = INHERIT,
    processes: ProcessPort = PROCESSES,
    supervisors: SupervisorPort | None = None,
    directories: ChannelDirectoryPort = CHANNEL_DIRECTORIES,
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
            never put in `env` (old SPEC decision-184/186).
        cwd: The command's working directory, inside a root of `policy`; the embedder's own
            when unset.
        stdio: Where the command's fd 0, 1 and 2 come from; the embedder's own by default.
        processes: The `ProcessPort` (a fake in a test).
        supervisors: A `SupervisorPort` to use as given (a fake in a test); `policy` is then not
            compiled and no supervisor script is written.
        directories: The `ChannelDirectoryPort`.
        proc_root: Where to scan for the jail's PID 1; `/proc` except in a test.

    Everything made before a failure (the script, the channel directory, the namespace fd, the
    placeholders) is removed before the exception propagates (TASK-0012). Beside what is listed
    below, the policy refusals of `_supervisors_for`, `StateDirectoryInvalid`, `JailSpawnFailed`
    from the driver (an unopenable stdio path included, TASK-0028), and
    `ChannelNamespaceNotFound` from `_namespace_fd_for` propagate. A jail whose command
    finished before its namespace was found has no namespace fd (TASK-0001.30).

    Raises:
        ChannelDirectoryCreateFailed: the host refused to create the channel
            directory.
        PlaceholdersFailed: the host refused a directory for an absent write deny or mask, or
            brig's record of it (TASK-0027).
    """
    if supervisors is not None:
        resolved_supervisors: SupervisorPort = supervisors
        supervisor_script: Path | None = None
        mounts: tuple[bwrap.Mount, ...] = ()
        absent: tuple[str, ...] = ()
    else:
        resolved_supervisors, supervisor_script, mounts, absent = _supervisors_for(
            policy, channels, cwd, stdio
        )
    channel_directory = (
        Path(channels.directory.host_path)
        if channels is not None and channels.reservations
        else None
    )
    created: Path | None = None
    namespace_fd: int | None = None
    record: Path | None = None
    state_dir = Path(resolved_state_dir())
    try:
        if absent:
            try:
                record = _placeholders.hold(state_dir, secrets.token_hex(8), absent)
            except OSError as error:
                raise PlaceholdersFailed(absent) from error
        if channel_directory is not None:
            try:
                directories.create(str(channel_directory))
            except OSError as error:
                raise ChannelDirectoryCreateFailed(str(channel_directory)) from error
            created = channel_directory
        plan = bwrap.compile_run(command, env=env)
        process = run(operations.create(plan, env_policy), processes, resolved_supervisors)
        if record is not None:
            try:
                _placeholders.attach(state_dir, record, process.pid)
            except OSError as error:
                raise PlaceholdersFailed(absent) from error
        if channel_directory is not None:
            namespace_fd = _namespace_fd_for(process, proc_root)
    except BaseException:
        if supervisor_script is not None:
            supervisor_script.unlink(missing_ok=True)
        if created is not None:
            try:
                directories.remove(str(created))
            except OSError:
                pass
        if namespace_fd is not None:
            close_namespace_fd(namespace_fd)
        if record is not None:
            try:
                _placeholders.release(state_dir, record)
            except OSError:
                pass  # left for the next jail's release to sweep
        raise
    return Jail(
        process=process,
        supervisors=resolved_supervisors,
        supervisor_script=supervisor_script,
        channel_directory=created,
        channel_namespace_fd=namespace_fd,
        mounts=mounts,
        placeholders=record,
        report=(
            bwrap.ceilings(policy, mounts, channels, _socket_directories())
            if mounts
            else frozendict()
        ),
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
            `infra.sockets.JAIL_PID1_TIMEOUT_S` passed, with `process` still running.
    """
    outcome = _sockets.jail_pid1_namespace(
        process.pid, time.monotonic() + _sockets.JAIL_PID1_TIMEOUT_S, proc_root
    )
    if isinstance(outcome, _sockets.JailPid1NotFound):
        raise ChannelNamespaceNotFound(process.pid)
    if isinstance(outcome, _sockets.JailPid1Exited):
        return None
    return outcome
