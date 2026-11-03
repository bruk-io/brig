"""Every exception brig's public API raises, one per failure (decision-0001 rule 13). Only
presentation calls infra, so only it catches an infra exception and raises one of these in its
place: an embedder never handles infra's."""

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


class PolicyStdioThroughLink(Exception):
    """Raised when a stdio path goes through a symbolic link: brig opens stdio files through no
    link at all, so a link swapped in by a jail cannot redirect them (TASK-0034)."""

    def __init__(self, path: str, link: str) -> None:
        super().__init__(
            f"stdio path {path!r} goes through the symbolic link {link!r} -- name the path it "
            "leads to (os.path.realpath) instead"
        )
        self.path = path
        self.link = link


class PolicyStdioNotOwnFile(Exception):
    """Raised when an existing stdio path is not a regular file the embedder owns: another
    user's file, or a device. brig writes and reads the command's streams only through the
    embedder's own files, or `/dev/null` (TASK-0035)."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"stdio path {path!r} is not a regular file you own -- use a fresh path brig "
            "creates, a file of your own, or /dev/null"
        )
        self.path = path


class PolicyStdioHardLinked(Exception):
    """Raised when an existing stdio file has another name (a hard link): appending to it would
    write to that other file too (TASK-0035)."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"stdio file {path!r} has another name (a hard link) -- remove it, or name a fresh "
            "path brig creates"
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
    deny or mask under a writable root, or its record of them (TASK-0027), or cannot note the
    started jail in that record. Whatever was made was removed again, and a jail already started
    was torn down first (TASK-0044); a teardown that left its group alive raises
    `JailTeardownFailed` instead, with this as its `__cause__`."""

    def __init__(self, paths: tuple[str, ...]) -> None:
        super().__init__(
            f"could not make the directories for {', '.join(map(repr, paths))} that the jail "
            "mounts over to hold them -- check the writable root's permissions and free space, "
            "and brig's state directory (BRIG_HOME)"
        )
        self.paths = paths


class ChannelDirectoryCreateFailed(Exception):
    """Raised when the host refused to create a jail's channel directory (a full disk, a
    permission, a `chmod` after the `mkdir`). The host's `OSError` is the `__cause__`; whatever
    was made before it is removed.

    Args:
        channel_dir: The channel directory's host path that could not be created.
    """

    def __init__(self, channel_dir: str) -> None:
        super().__init__(
            f"could not create the channel directory {channel_dir!r} -- check the free space and "
            "permissions of brig's state directory (BRIG_HOME), where channel directories are made"
        )
        self.channel_dir = channel_dir


class StateDirectoryInvalid(Exception):
    """Raised when `BRIG_HOME` is not an absolute path.

    Args:
        value: The `BRIG_HOME` value refused.
    """

    def __init__(self, value: str) -> None:
        super().__init__(f"BRIG_HOME is not usable as brig's own state directory: {value!r}")
        self.value = value


class JailSpawnFailed(Exception):
    """Raised when a jail's supervisor could not be started (an unopenable stdio path
    included).

    Args:
        argv: The command the jail was to run.
    """

    def __init__(self, argv: tuple[str, ...]) -> None:
        super().__init__(f"could not spawn jail process: {argv!r}")
        self.argv = argv


class JailWaitTimedOut(Exception):
    """Raised when a jail's command did not finish before the wait's deadline. The jail still
    runs.

    Args:
        process: The jail's supervisor.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail process did not exit before its deadline: {process!r}")
        self.process = process


class JailExitUnknown(Exception):
    """Raised when a jail's exit code can never be recovered: the supervisor's report is gone
    (its pipe closed with no `done`, or could not be read). Waiting again will not help.

    Args:
        process: The jail's supervisor.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail's exit code was lost before it was reported: {process!r}")
        self.process = process


class JailTeardownFailed(Exception):
    """Raised when a jail's process group was still alive after TERM, KILL and the grace poll:
    by `destroy_jail`, and by `create_bwrap_jail` when a step after the start failed and the
    teardown that followed could not end the jail (that step's error is the `__cause__`).

    Args:
        process: The jail's supervisor, whose group is still alive.
    """

    def __init__(self, process: Process) -> None:
        super().__init__(f"jail's process group still alive after teardown: {process!r}")
        self.process = process


class ChannelNamespaceNotFound(Exception):
    """Raised when a jail that declared channels started but no in-jail PID 1 appeared under
    its bwrap before `infra.sockets.JAIL_PID1_TIMEOUT_S` passed: readiness has no namespace to
    compare a peer against (decision-0005 item 1), or `/proc` could not be listed (the
    `OSError` is the `__cause__`). The started jail was torn down before this propagates
    (TASK-0044).

    Args:
        bwrap_pid: The outer bwrap process whose children were scanned.
    """

    def __init__(self, bwrap_pid: int) -> None:
        super().__init__(
            f"no in-jail PID 1 found under the jail's own bwrap process {bwrap_pid}: "
            f"readiness has no PID namespace to compare a peer against"
        )
        self.bwrap_pid = bwrap_pid


class ChannelNameRefused(Exception):
    """Raised by `reserve_channels` when a channel's name would not name exactly one file in the
    channel directory (empty, `.` or `..`, containing `/` or NUL, or a repeat). Nothing was
    reserved.

    Args:
        name: The refused channel name.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"channel name {name!r} would escape or repeat in the jail's channel "
            f"directory -- name each channel with one distinct path component"
        )
        self.name = name
