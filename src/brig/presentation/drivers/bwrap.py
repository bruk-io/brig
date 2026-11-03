"""The bwrap jail type's presentation (decision-0001 rule 3, decision-0007 item 5): writing the
supervisor script, refusing and compiling the policy, starting the jail through the shared driver,
and holding the jail's PID namespace for channel readiness."""

import secrets
import sys
import tempfile
import time
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
    StdioInWritableRoot,
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
    PolicyStdioInWritableRoot,
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
    """Where this host's own assembled supervisor file actually is: rule 17's
    one file (`infra.supervisor.assemble.assembled_source()` -- `wire.py` +
    `program.py`, stdlib only, refusing to run under an interpreter older
    than 3.15), written fresh to a new file inside brig's own state directory
    (`resolved_state_dir`, TASK-0006) on every call.

    TASK-0001.21: no longer `functools.cache`d -- every jail needs its own
    file, so that `destroy_jail` can delete exactly the one file it no longer
    needs without also deleting a still-live jail's own (`_supervisors_for`'s
    own docstring has the reasoning). Never called at module scope: writing a
    file is real I/O, and `pyproject.toml`'s own `[tool.pypeeker.import-time-
    side-effects]` allow-list has no entry for this module, so doing this
    eagerly at import time would trip that rule, not just style. Called
    exactly once per `create_bwrap_jail` call that needs it (`_supervisors_for`,
    the one caller) -- a second call in the same jail's creation would write a
    second, decoy file and leak the first one forever once `destroy_jail`
    deletes the wrong path instead.

    Reachable inside a bwrap jail under most of the caller's own `policy` shapes (TASK-0006):
    `compile_supervisor_launch` masks `resolved_state_dir()` unconditionally and binds this one
    file back inside it (TASK-0019), so wherever `tempfile.NamedTemporaryFile`'s own collision-safe
    random suffix actually placed this file stays reachable even under a policy that excludes
    everything else this file used to depend on (`/tmp`, before this task; the whole host root,
    under `WHOLE_HOST_READ_ONLY`, incidentally covered it too). A jail created with a narrower
    `policy` of its own no longer has to also happen to cover this path -- that was exactly
    TASK-0006's bug.

    `-I` (isolated mode, TASK-0001.15/.17 adversarial review) runs this
    interpreter ignoring `PYTHONPATH`/`PYTHONHOME` and without adding user
    site-packages, regardless of what this process's own environment happens
    to carry -- belt and braces next to `infra.supervisor.link._start` no
    longer handing the supervisor process `EnvPolicy`-scrubbed environment at
    all (that module's own docstring explains why a mapping an embedder
    scrubbed for the *confined command* is not safe to also hand the process
    enforcing the confinement): `-I` closes the same hole a second,
    independent way, for whatever this process's own environment might
    someday carry. It does nothing for `LD_PRELOAD`, which the dynamic linker
    consults before the interpreter ever starts -- the env split is what
    closes that half. The assembled file imports only the stdlib (rule 17),
    so running it under `-I` changes nothing it does.
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
    """The `SupervisorPort` `create_bwrap_jail` uses for `policy` when its caller names none,
    the path of the fresh supervisor script written for it (TASK-0001.21: the jail deletes
    that one file and no other), and the mounts the jail was compiled with.

    A fresh `LiveSupervisors` every call: whichever instance opened a jail's events pipe is
    the only one that can read or close it, and `Jail.supervisors` carries it back to
    `run_jail`/`destroy_jail`.

    Refuses `policy` before anything is written (`domain/policy/paths.py`'s `refusal`, with
    the state directory and the channel directory as paths the jail needs), then looks up
    what is at each write deny's and mask's path, the one host fact the compile needs.

    Raises:
        PolicyPathNotAbsolute: a path in `policy` is not absolute and normalised.
        PolicyMaskHides: a mask hides a root, the state directory or the channel directory.
        PolicyRootAbsent: a readable or writable root does not exist on the host.
        PolicyPathThroughLink: an entry is reached through a symbolic link inside a writable
            root.
        PolicyCwdOutsideRoots: `cwd` is in no root of the policy.
        PolicyStdioInWritableRoot: a stdio path is inside a writable root.
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
    match stdio_refusal(policy, streams, chains):
        case PathNotAbsolute(path=path):
            raise PolicyPathNotAbsolute(path)
        case StdioInWritableRoot(path=path):
            raise PolicyStdioInWritableRoot(path)
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
    port = real_supervisor_port(link.LiveSupervisors(supervisor_argv, streams))
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
    env: tuple[tuple[str, str], ...] = (),
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
    """Compile `command` into a bwrap jail and start its supervisor running it,
    seeing exactly the paths `policy` names (TASK-0001.16) and exactly the
    environment variables `env_policy` allows out of `env` (TASK-0001.17).

    `policy` defaults to `WHOLE_HOST_READ_ONLY` (`domain/policy/paths.py`), the
    same whole host root, read-only, every jail got before that parameter existed.
    `env` is the candidate environment (`Plan.env`'s own docstring: not yet
    scrubbed) a caller has to offer; left unset, it is empty, so `env_policy`
    defaults to `DENY_ALL` (`domain/policy/env.py`) and scrubs nothing out of
    nothing -- the same no-environment-at-all behaviour every jail got before
    either parameter existed, now reached by an explicit policy rather than a
    bare default with no policy behind it. `operations.create` is the one place
    `env_policy` is ever applied (`domain/operations.py`'s own docstring): by the
    time this function's own `run` performs the yielded `StartSupervisedCommand`,
    the effect's `env` is already scrubbed, and nothing downstream (this driver,
    `infra/supervisor/link.py`) ever reads `env` or `os.environ` again to get
    there.

    `cwd` is the command's working directory (bwrap's `--chdir`; inside a root of `policy`,
    else `PolicyCwdOutsideRoots`), the embedder's own when left unset. `stdio` says where the
    command's fd 0, 1 and 2 come from (`domain/policy/stdio.py`), the embedder's own by default;
    a path that cannot be opened is `JailSpawnFailed` (TASK-0028).

    `channels` is what `reserve_channels` handed back for this jail (TASK-0001.25):
    its channel directory is bound into the jail, writable, when it declares any
    channel. It reaches the jailed command only through `command` -- the caller has
    already written each endpoint there -- and never through `env`, which this
    function neither reads nor extends with it (old SPEC decision-184/186). The
    directory itself is created here (TASK-0001.26), through `directories`, when
    `channels` declares any channel: private to the owning user, under brig's own
    state directory, before the jail starts (it is the channel bind's source;
    the jail sees it through the state directory's mask, TASK-0019). It is carried on
    the returned `Jail` as `channel_directory` for `destroy_jail` to remove.

    `supervisors`, left unset, is resolved from `policy` (`_supervisors_for`),
    which also writes this jail's own fresh supervisor script file and hands
    back its path, carried on the returned `Jail` as `supervisor_script` for
    `destroy_jail` to delete later (TASK-0001.21). An explicit `supervisors` (a
    fake, in a test) is used as given instead, and `policy` then plays no part,
    the same way a fake stands in for the whole world regardless of what domain
    state asked for it -- no file was written for it, so `supervisor_script` is
    `None` on the `Jail` this returns.

    `presentation/driver.py`'s `run` raises `JailSpawnFailed` should the
    supervisor's own start fail. Resolving brig's own state directory
    (`resolved_state_dir`, above) raises `StateDirectoryInvalid` should
    `BRIG_HOME` name a value it cannot use. `_supervisors_for` raises
    `PolicyPathNotAbsolute` or `PolicyMaskHides` for a policy it refuses
    (decision-0007), while `_namespace_fd_for` (below) raises
    `ChannelNamespaceNotFound` for a channel-declaring jail whose in-jail PID 1
    never appears while its outer process still runs (TASK-0001.27); one whose
    command already finished returns a `Jail` with no namespace fd instead
    (TASK-0001.30). `directories.create`'s own `OSError` (a full or
    read-only disk) is raised as `ChannelDirectoryCreateFailed`, with the
    `OSError` as its `__cause__` (TASK-0001.29). Nothing else in this
    function's own body raises, so nothing else is in this docstring.

    TASK-0012: once `_supervisors_for` has written `supervisor_script`, no `Jail`
    exists yet to carry that path to a later `destroy_jail` call -- this is the
    only function that still holds it. Should `run` raise anything at all before
    returning (`JailSpawnFailed`, the one documented case, but this catches
    unconditionally rather than naming it, so a future failure added to that call
    is never a second leak to rediscover), the just-written file is deleted here
    before the exception propagates unchanged: a side effect alongside the raise,
    never a replacement for it.

    TASK-0001.26: `directories.create` runs inside that same `try`, not before it,
    because it can itself fail partway (`mkdir` succeeds, `chmod` does not) -- a
    directory created outside the `try` would leak exactly like the script did.
    The `except` therefore removes the channel directory too, swallowing `OSError`
    the same way `destroy_jail` does (and safe when `create` never finished:
    `remove` on a path `mkdir` already made still finds something to delete),
    before the original exception propagates. `Jail.channel_directory` is set only
    once `create` returned.

    TASK-0001.27: for a jail that declares a channel, the jail's own PID namespace
    is looked up here too, once the supervisor has actually started (`process.pid`
    -- the *outer* bwrap process -- is what the scan is rooted at), inside the same
    `try` and for the same leak reason as `directories.create`: a
    `ChannelNamespaceNotFound` must not leave the channel directory or the script
    behind either -- and should anything later in the same `try` raise, the
    namespace fd this call already opened is closed on the way out, so a failure
    here leaks neither a directory, nor a script, nor an fd.
    `infra.sockets.jail_pid1_namespace` is called directly rather than through a
    port (`ChannelReadinessPort`'s own docstring: nothing needs to fake "which pid
    is bwrap's child"). The resulting fd is carried as `Jail.channel_namespace_fd`.

    `proc_root` is `/proc` for every production caller, and is passed straight
    through to `_namespace_fd_for`: it exists so a test can plant a directory tree
    of its own rather than need a real bwrap jail underneath the scan, the same
    parameter `infra.processes.group_alive` already carries (TASK-0016).

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
                _placeholders.attach(record, process.pid)
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
        report=bwrap.ceilings(policy, mounts, channels) if mounts else {},
    )


def _namespace_fd_for(process: Process, proc_root: str = "/proc") -> int | None:
    """The open fd on the jail's own PID namespace, found under `process` -- the
    *outer* bwrap process `create_bwrap_jail` just started -- or `None` when the
    jail's command had already finished and taken that namespace with it
    (TASK-0001.30: `infra.sockets.JailPid1Exited`, which the scan reports as soon as
    `process` itself is gone, without waiting out its deadline), or
    `ChannelNamespaceNotFound` once `infra.sockets.JAIL_PID1_TIMEOUT_S` passes with
    `process` still running and no in-jail PID 1 in sight.

    `infra.sockets.jail_pid1_namespace` is called with a `time.monotonic()`
    deadline computed here, never with that module's own constant: infra takes a
    deadline rather than computing one, the same split `infra.processes.
    reap_deadline` already has (rule 2: the module that decides what "too long"
    means is presentation's, the one that waits is infra's).

    That deadline (and so the frozen duration it is built from) is what this
    function adds to `create_bwrap_jail`'s own documented failure set, alongside
    the `ChannelDirectoryCreateFailed` its `directories.create` call can already
    raise.

    Raises:
        ChannelNamespaceNotFound: nothing under `process.pid` looked like the jail's
            in-jail PID 1 before the deadline passed.

    `proc_root` is `/proc` for every production caller; it exists so a test can plant
    a directory tree of its own instead of a real bwrap jail, the same parameter
    `infra.processes.group_alive` already carries for the same reason (TASK-0016).
    """
    outcome = _sockets.jail_pid1_namespace(
        process.pid, time.monotonic() + _sockets.JAIL_PID1_TIMEOUT_S, proc_root
    )
    if isinstance(outcome, _sockets.JailPid1NotFound):
        raise ChannelNamespaceNotFound(process.pid)
    if isinstance(outcome, _sockets.JailPid1Exited):
        return None
    return outcome
