"""Exceptions brig's public API can raise for the bwrap walking skeleton (decision-0001
rule 13).

One subclass per failure. `presentation/driver.py`, `presentation/drivers/bwrap.py`,
`presentation/jail.py` and `presentation/api.py` are the only modules that call infra, so
they are the only ones that catch an infra exception and raise one of these in its
place -- an embedder handles brig's own types without ever needing infra's.
"""

from brig.domain.effects import Process


class PolicyPathNotAbsolute(Exception):
    """Raised when a path in a caller's `FsPolicy` is not absolute and normalised: a policy
    names each path as it is on the host and in the jail (decision-0007)."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"policy names {path!r}, which is not an absolute, normalised path -- write it as "
            "it is on the host, starting with / and with no '.', '..' or empty component"
        )
        self.path = path


class PolicyMaskHides(Exception):
    """Raised when a mask in a caller's `FsPolicy` hides a path the jail must see: one of
    the policy's roots, or brig's own state or channel directory. A mask is an empty
    read-only directory, so nothing beneath it can be mounted (decision-0007)."""

    def __init__(self, mask: str, path: str) -> None:
        super().__init__(
            f"policy masks {mask!r}, which hides {path!r} beneath it -- mask the paths inside "
            f"{mask!r} you mean to hide instead, or set BRIG_HOME outside it if {path!r} is "
            "brig's own state directory"
        )
        self.mask = mask
        self.path = path


class PolicyCwdOutsideRoots(Exception):
    """Raised when the working directory a caller gives `create_bwrap_jail` is in no readable or
    writable root of its policy: it would not exist in the jail (TASK-0028)."""

    def __init__(self, cwd: str) -> None:
        super().__init__(
            f"cwd {cwd!r} is in no root of the policy, so it does not exist in the jail -- add a "
            "readable or writable root that contains it, or start the command elsewhere"
        )
        self.cwd = cwd


class PolicyStdioInWritableRoot(Exception):
    """Raised when a stdio path a caller gives `create_bwrap_jail` is inside a writable root of
    its policy: a jail may write there, so it could swap the file for a link and have a later
    jail's output written into any file the embedder can write (TASK-0031)."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"stdio path {path!r} is inside a writable root of the policy, where a jail could "
            "replace it with a link -- put the command's streams somewhere no jail can write"
        )
        self.path = path


class PolicyInterpreterUnreachable(Exception):
    """Raised when the policy does not mount the interpreter brig runs its supervisor under
    (this process's own), or a link on the way to it: the supervisor could not start
    (TASK-0029)."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"the jail's supervisor runs under this interpreter, and the policy does not mount "
            f"{path!r} on the way to it -- add a readable root that contains it (and every link "
            "it goes through, such as a version-manager's link to its install directory)"
        )
        self.path = path


class PolicyRootAbsent(Exception):
    """Raised when a readable or writable root in a caller's `FsPolicy` does not exist on the
    host: a root is mounted from where it is, so it has to be there (decision-0007)."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"policy names {path!r} as a root, and nothing is there on the host -- create it "
            "before the jail starts, or leave it out of the policy"
        )
        self.path = path


class PolicyPathThroughLink(Exception):
    """Raised when an entry in a caller's `FsPolicy` is reached through a symbolic link inside a
    writable root: the command may replace that link, and a mount follows it, so the entry would
    protect the link's target and not the path (TASK-0025)."""

    def __init__(self, path: str, root: str) -> None:
        super().__init__(
            f"policy names {path!r}, which is reached through a symbolic link inside the writable "
            f"root {root!r}; the command could replace that link, so nothing at {path!r} would "
            "hold -- name the path the link leads to instead, or replace the link with what it "
            "points at"
        )
        self.path = path
        self.root = root


class PlaceholdersFailed(Exception):
    """Raised when brig cannot make, on the host, the directories it mounts over an absent write
    deny or mask under a writable root, or its record of them (TASK-0027): nothing was started,
    and whatever was made was removed again."""

    def __init__(self, paths: tuple[str, ...]) -> None:
        super().__init__(
            f"could not make the directories for {', '.join(map(repr, paths))} that the jail "
            "mounts over to hold them -- check the writable root's permissions and free space, "
            "and brig's state directory (BRIG_HOME)"
        )
        self.paths = paths


class ChannelDirectoryCreateFailed(Exception):
    """Raised when the host refused to create a jail's per-jail channel directory
    (TASK-0001.29): a full disk, a permissions change under brig's own state
    directory, or a `chmod` that failed after its `mkdir` had succeeded.

    The host filesystem's own `OSError` is the `__cause__`, so the reason is
    never lost, but an embedder handles this one type and never sees `infra`'s
    exception (the driver exception boundary, decision-0001 rules 9 and 13).
    Whatever had been started or written before the failure is cleaned up first,
    the same as for every other failure out of `create_bwrap_jail`.

    Args:
        channel_dir: The channel directory's host path that could not be created.
    """

    def __init__(self, channel_dir: str) -> None:
        super().__init__(f"could not create the channel directory {channel_dir!r}")
        self.channel_dir = channel_dir


class StateDirectoryInvalid(Exception):
    """Raised when `BRIG_HOME` names a value brig's own state directory cannot
    use (`infra/state_dir.py`'s `resolve`) -- translated here from infra's own
    `ValueError`, the one place this module's driver-exception-boundary rule
    says that happens (an embedder handles brig's own types without ever
    seeing `infra`'s).

    Args:
        value: The offending `BRIG_HOME` value `resolve` refused -- not an
            absolute path.
    """

    def __init__(self, value: str) -> None:
        super().__init__(f"BRIG_HOME is not usable as brig's own state directory: {value!r}")
        self.value = value


class JailSpawnFailed(Exception):
    """Raised when a jail's one process could not be started.

    Args:
        argv: The command that could not be run as the jail's process.
    """

    def __init__(self, argv: tuple[str, ...]) -> None:
        super().__init__(f"could not spawn jail process: {argv!r}")
        self.argv = argv


class JailWaitTimedOut(Exception):
    """Raised when waiting for a jail's process to exit passed its deadline.

    Args:
        process: The jail's process, whose exit wait passed its deadline with the
            process still unreaped.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail process did not exit before its deadline: {process!r}")
        self.process = process


class JailExitUnknown(Exception):
    """Raised when a jail's process's exit code could not be collected because
    something else reaped it first.

    Args:
        process: The jail's process, no longer this program's child to wait for at
            all (`ECHILD`) by the time `run_jail` waited on it -- an embedder that
            auto-reaps its own children, or a signal disposition that discards them,
            is the usual cause. Unlike `JailWaitTimedOut`, retrying the wait can never
            succeed: the exit code is gone for good.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail process already reaped elsewhere, exit code lost: {process!r}")
        self.process = process


class JailTeardownFailed(Exception):
    """Raised when a jail's process group was still alive after the kill ladder.

    Args:
        process: The jail's process, whose group the kill ladder's last verify still
            found alive after signalling it with both TERM and KILL.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail's process group still alive after teardown: {process!r}")
        self.process = process


class ChannelNamespaceNotFound(Exception):
    """Raised when a jail that declared channels started, but no in-jail PID 1
    could be found under the process `create_bwrap_jail` started, before
    `infra.sockets.JAIL_PID1_TIMEOUT_S` passed (TASK-0001.27).

    A creation failure, not a readiness result: readiness compares a peer against
    the jail's own PID namespace (decision-0005 item 1), so a jail that cannot
    offer one cannot answer "is this channel ready" at all, and the three
    per-poll outcomes (`ChannelReady`/`ChannelNotReady`/`ChannelRefused`) would
    have nothing to say about it.

    Should not happen with `--as-pid-1`, which makes the jailed program PID 1
    inside its own namespace by construction (`domain/jail_types/bwrap.py`'s own
    docstring), and TASK-0001.24 measured bwrap forking into exactly that shape on
    every run -- but nothing proves it cannot, so it is refused loudly here rather
    than hanging `create_bwrap_jail` past its own deadline.

    Args:
        bwrap_pid: The outer bwrap process `create_bwrap_jail` started, whose
            `/proc` children were scanned for the jail's own PID 1.
    """

    def __init__(self, bwrap_pid: int) -> None:
        super().__init__(
            f"no in-jail PID 1 found under the jail's own bwrap process {bwrap_pid}: "
            f"readiness has no PID namespace to compare a peer against"
        )
        self.bwrap_pid = bwrap_pid


class ChannelNameRefused(Exception):
    """Raised by `reserve_channels` when a declared channel's name would not name
    exactly one file inside the jail's channel directory -- empty, `.` or `..`,
    containing `/` or NUL, or repeating an earlier channel's name
    (`domain/channels.py`'s `reserve`, TASK-0001.25). Nothing has been reserved or
    started when this is raised.

    Args:
        name: The refused channel name.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"channel name {name!r} would escape or repeat in the jail's channel "
            f"directory -- name each channel with one distinct path component"
        )
        self.name = name
