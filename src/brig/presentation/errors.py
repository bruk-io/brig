"""Every exception brig's public API raises, one per failure (decision-0001 rule 13). Only
presentation calls infra, so only it catches an infra exception and raises one of these in its
place: an embedder never handles infra's."""

from brig.domain.effects import Process
from brig.domain.policy.egress import Destination


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


class PolicyPathUninspectable(Exception):
    """Raised when brig could not inspect a path it must judge before a jail starts: an entry of
    a caller's `FsPolicy`, a stdio path, or the interpreter the supervisor runs under. The host
    refused to say what is there or where a link on the way leads (a directory the embedder's
    user cannot search, a symbolic link loop, a link it cannot read or that changed while brig
    read it). The host's `OSError` is the `__cause__`; nothing was made or started (TASK-0047).

    Args:
        path: The path as the caller named it.
    """

    def __init__(self, path: str) -> None:
        super().__init__(
            f"could not inspect {path!r} on the host, so brig cannot tell what a jail would see "
            "there -- make every directory on the way searchable by this process's user and "
            "every link on it readable and not a loop, or leave the path out"
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


class PolicyEgressHostEmpty(Exception):
    """Raised when a `Destination` in a caller's `EgressPolicy` names no host (decision-0009
    item 3).

    Args:
        destination: The refused entry.
    """

    def __init__(self, destination: Destination) -> None:
        super().__init__(
            f"egress policy grants {destination!r}, which names no host -- name a hostname, "
            "*.suffix, or an IP address"
        )
        self.destination = destination


class PolicyEgressPortOutOfRange(Exception):
    """Raised when a `Destination` in a caller's `EgressPolicy` has a port that is not a whole
    number from 1 to 65535. A grant always names one port; there are no port wildcards
    (decision-0009 item 3).

    Args:
        destination: The refused entry.
    """

    def __init__(self, destination: Destination) -> None:
        super().__init__(
            f"egress policy grants {destination!r}, whose port is not from 1 to 65535 -- name "
            "the one port the jail may reach there, and grant each other port on its own"
        )
        self.destination = destination


class PolicyEgressLimitOutOfRange(Exception):
    """Raised when an `EgressLimits` field is not above zero, or is above the default it may
    only lower (TASK-0049): a limit bounds what a jail's egress route may hold of the host, so
    an embedder can tighten it, for a test or a small jail, and never loosen it.

    Args:
        name: The field.
        value: What it was given.
        ceiling: Its default, the most it may be.
    """

    def __init__(self, name: str, value: float, ceiling: float) -> None:
        super().__init__(
            f"egress limit {name}={value!r} is out of range -- give a value above 0 and at most "
            f"{ceiling!r}, its default; a limit can be lowered, never raised"
        )
        self.name = name
        self.value = value
        self.ceiling = ceiling


class PolicyEgressWildcardMisplaced(Exception):
    """Raised when a `Destination`'s host in a caller's `EgressPolicy` has a `*` anywhere but as
    its whole first label (decision-0009 item 3).

    Args:
        destination: The refused entry.
    """

    def __init__(self, destination: Destination) -> None:
        super().__init__(
            f"egress policy grants {destination!r}, with a wildcard brig cannot read -- the one "
            "wildcard is a leading '*.' (as in '*.example.com', the names under it and not "
            "example.com itself); grant other names exactly"
        )
        self.destination = destination


class PolicyEgressCidr(Exception):
    """Raised when a `Destination`'s host in a caller's `EgressPolicy` is an address range in
    CIDR notation: a grant names one address (decision-0009 item 3).

    Args:
        destination: The refused entry.
    """

    def __init__(self, destination: Destination) -> None:
        super().__init__(
            f"egress policy grants {destination!r}, an address range -- grant each address "
            "the jail may reach on its own, without a '/' prefix length"
        )
        self.destination = destination


class PolicyEgressHostInvalid(Exception):
    """Raised when a `Destination`'s host in a caller's `EgressPolicy` is neither an IP literal
    nor a valid hostname: labels of 1 to 63 ASCII letters, digits and hyphens with no hyphen at
    either end, 253 characters at most, and a last label that is not a number (decision-0009
    item 3).

    Args:
        destination: The refused entry.
    """

    def __init__(self, destination: Destination) -> None:
        super().__init__(
            f"egress policy grants {destination!r}, whose host is no valid hostname or IP "
            "address -- write a name in ASCII (an internationalised one in its xn-- form), an "
            "IPv4 address as four decimal numbers, and an IPv6 address without a zone"
        )
        self.destination = destination


class PolicyEgressNeedlessBrackets(Exception):
    """Raised when a `Destination`'s host in a caller's `EgressPolicy` is bracketed: a
    `Destination` holds its port apart, so an IPv6 address needs no brackets (decision-0009
    item 3).

    Args:
        destination: The refused entry.
    """

    def __init__(self, destination: Destination) -> None:
        super().__init__(
            f"egress policy grants {destination!r}, a bracketed host -- name the IPv6 address "
            "without its brackets, as in Destination('::1', 443)"
        )
        self.destination = destination


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


class StateDirectoryWriteFailed(Exception):
    """Raised when the host refused what brig makes in its own state directory (`BRIG_HOME`,
    else `~/.brig`) before a jail starts: the directory itself, the empty read-only directory a
    jail mounts over what it masks, or the jail's supervisor script (a full disk, a file size
    limit, a permission, something already at the path). The host's `OSError` is the
    `__cause__`; nothing was started, and a script written in part was removed (TASK-0046).

    Args:
        path: What could not be made or written: the state directory, or its empty directory.
    """

    def __init__(self, path: str) -> None:
        super().__init__(
            f"could not make or write {path!r} in brig's state directory -- check its free "
            "space, permissions and file size limit, and that its 'empty' directory holds "
            "nothing, or set BRIG_HOME to an absolute path brig can write"
        )
        self.path = path


class SupervisorSourceUnreadable(Exception):
    """Raised when brig could not read its own supervisor program's source, which it assembles
    into each jail's supervisor script: brig's install is incomplete or unreadable, not its
    state directory. The host's `OSError` is the `__cause__` and names the file; nothing was
    written or started (TASK-0047)."""

    def __init__(self) -> None:
        super().__init__(
            "could not read brig's own supervisor source (brig.infra.supervisor's wire.py and "
            "program.py) -- brig's install is incomplete or unreadable by this process's user; "
            "reinstall brig"
        )


class EgressProxySourceUnreadable(Exception):
    """Raised when brig could not read its own egress proxy's source, which it assembles into
    each egress proxy (decision-0009 item 2): brig's install is incomplete or unreadable. The
    host's `OSError` is the `__cause__` and names the file; nothing was written or started."""

    def __init__(self) -> None:
        super().__init__(
            "could not read brig's own egress proxy source (brig.infra.proxy's program.py and "
            "brig.domain.policy's egress.py) -- brig's install is incomplete or unreadable by "
            "this process's user; reinstall brig"
        )


class PolicyEnvNamesProxyVariable(Exception):
    """Raised when a jail is created with an `EgressPolicy` and an `EnvPolicy` that allows one
    of the proxy variables the jail sets itself (decision-0009 item 7): refused rather than
    silently overridden.

    Args:
        name: The proxy variable the environment policy allows.
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"environment policy allows {name!r}, which a jail with an egress policy sets "
            "itself to its own proxy -- remove it from the EnvPolicy; the command reaches the "
            "network only through brig's proxy, whatever proxy the embedder's environment names"
        )
        self.name = name


class JailSpawnFailed(Exception):
    """Raised when a jail's supervisor could not be started (an unopenable stdio path
    included). A `SupervisorPort` raises it itself, with `process` set, when the supervisor
    was spawned and a later step of its start failed (TASK-0046).

    Args:
        argv: The command the jail was to run.
        process: The supervisor spawned before the start failed, which `create_bwrap_jail`
            tears down before this propagates; `None` when nothing was spawned.
    """

    def __init__(self, argv: tuple[str, ...], process: Process | None = None) -> None:
        super().__init__(f"could not spawn jail process: {argv!r}")
        self.argv = argv
        self.process = process


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
    """Raised when a jail's process group was still alive after TERM, KILL and the grace poll,
    or the teardown itself raised so the group could not be verified gone: by `destroy_jail`
    (the teardown's own error, if any, is the `__cause__`), and by `create_bwrap_jail` when a
    step after the spawn failed and the teardown that followed could not end the jail (that
    step's error is the `__cause__`, with the teardown's own failure added to it as a note,
    TASK-0046).

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


class JailHasNoEgress(Exception):
    """Raised by `allow_egress`, `revoke_egress`, `egress_decisions` and `egress_record` for a jail
    with no egress proxy: one created without an `EgressPolicy`, which has loopback and nothing
    else, or built with a caller's own `supervisors`, which starts none (decision-0009 item 5)."""

    def __init__(self) -> None:
        super().__init__(
            "this jail has no egress proxy to grant to or read from: it was created without an "
            "EgressPolicy -- create it with create_bwrap_jail(..., egress=EgressPolicy(...)), an "
            "empty one if it should start with nothing granted"
        )


class JailEgressEnded(Exception):
    """Raised by `allow_egress` and `revoke_egress` when the jail's egress proxy has ended: its
    command finished (`run_jail` saw it), `destroy_jail` ran, or the proxy died. Nothing was
    sent or recorded.

    Args:
        destination: The destination the call named.
    """

    def __init__(self, destination: Destination) -> None:
        super().__init__(
            f"the jail's egress proxy has ended, so {destination.host}:{destination.port} "
            "cannot be granted or revoked -- a grant reaches a jail only while its command runs; "
            "put the destination in the EgressPolicy of the next jail instead"
        )
        self.destination = destination
