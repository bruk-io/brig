"""The per-jail channel directory's lifecycle on the real filesystem (TASK-0001.26):
create it, private to the owning user, and remove it once a jail is done with it --
plus, since TASK-0001.27, the verified connect that says whether a channel is ready:
a `connect` that succeeds *and* is confirmed, by PID namespace, to have reached a
process inside the jail's own (decision-0005 item 1), never path existence.

Imports nothing from `brig` (`brig-layers`'s own `infra` allow-list is empty) and takes
and returns plain data -- a host path or a pid, as plain values, the same shape
`presentation/ports.py`'s `ChannelDirectoryPort`/`ChannelReadinessPort` already use.

`jail_pid1_namespace` and `channel_ready` are the two halves decision-0005 item 1
splits readiness into: finding and holding the jail's own PID namespace once, at jail
start, and verifying one connect against it, every poll. The algorithm in both is
TASK-0001.24's own measured probe, adapted rather than re-derived -- the spike's
`jail_pid_ns` (the child scan, below) and `verified_ready` (`channel_ready`) are that
probe's own code, and decision-0005 item 1 states what each step is for.
"""

import errno
import os
import shutil
import socket
import stat
import struct
import time
from dataclasses import dataclass
from pathlib import Path

SO_PEERPIDFD = getattr(socket, "SO_PEERPIDFD", 77)
"""`SOL_SOCKET`'s `SO_PEERPIDFD` (Linux 6.5+), or the literal number Linux assigns it
where this interpreter's own `socket` module has no name for it.

The fallback is TASK-0001.24's probe, kept verbatim: the constant is a kernel ABI
number, so hardcoding it is not a guess -- but it is also not the same fact as "this
kernel has the option", which is only ever learned by asking for it, below. See
`channel_ready`'s own docstring for why the two are kept distinct rather than
collapsed into one refusal.
"""

_POLL_INTERVAL_S = 0.05
"""How often `jail_pid1_namespace` re-scans for the jail's own PID 1, matching
`processes._POLL_INTERVAL_S`'s role as this package's own "short enough to honour a
deadline, long enough not to spin" number. Larger than that one on purpose: each
iteration here lists and reads all of `/proc`, which is orders of magnitude dearer
than the single syscall `processes` polls with, and the window it waits on is wider
(bwrap forking into a new PID namespace, not a signal landing).
"""

JAIL_PID1_TIMEOUT_S = 5.0
"""How long `jail_pid1_namespace` keeps looking for the jail's in-jail PID 1 before
giving up.

TASK-0001.24's own probe as provenance, not a rounder number picked here: its
`jail_pid_ns` helper used `deadline = time.monotonic() + 5`, measured sufficient on
real bwrap for an `--as-pid-1` jail to produce its in-jail PID 1. Change it only
against a fresh measurement. Public because `presentation/api.py` is what computes
the deadline it is handed (`jail_pid1_namespace` takes a deadline, never reads this
itself -- rule 2: infra waits, presentation decides how long).
"""


@dataclass(frozen=True)
class JailPid1NotFound:
    """Sentinel `jail_pid1_namespace` returns in place of a namespace fd when no
    process matching the jail's own in-jail PID 1 appears under `bwrap_pid` before
    its deadline passes.

    Infra hands back plain data and never raises a `brig` type (decision-0001
    rules 1 and 9), the same reasoning `infra/processes.py`'s own `ProcessUnknown`
    sentinel gives; `presentation/api.py` is the one place that turns this into a
    typed exception (`ChannelNamespaceNotFound`), because a jail that cannot offer
    the namespace readiness compares against is a creation failure, never a
    per-poll result.
    """


@dataclass(frozen=True)
class JailPid1Exited:
    """Sentinel `jail_pid1_namespace` returns when no in-jail PID 1 was found and
    the outer process it was looked for under is itself gone (or a zombie): the
    jail's whole namespace is gone with it, so nothing will ever appear
    (TASK-0001.30).

    Distinct from `JailPid1NotFound`, which is the outer process still running but
    no PID 1 showing up before the deadline -- a creation failure. This is not a
    failure of the lookup: a supervised command that finishes in milliseconds takes
    its supervisor (the in-jail PID 1) and so bwrap down with it, before any
    host-side scan can win the race to it.
    """


@dataclass(frozen=True)
class ChannelReady:
    """A channel is ready: this connect reached a socket whose listening process is
    inside the jail's own PID namespace (decision-0005 item 4 -- it proves a
    process in that namespace called `listen()` on it, and nothing more).
    """


@dataclass(frozen=True)
class ChannelNotReady:
    """Nothing is listening at the channel's path yet: `connect` itself failed, so
    nothing about a peer was reached at all. A transient state worth polling
    through, unlike a refusal.
    """


@dataclass(frozen=True)
class ChannelRefused:
    """`channel_ready`'s refusal: `reason` is one of the three names below. Terminal
    for the connection it describes -- a consumer that reconnects must verify again
    (decision-0005 item 1) -- and returned, never raised.

    Three plain module-level string constants, not an `Enum`: `Enum` is a `brig`
    concept for values that cross into domain and presentation, and this module
    imports nothing from `brig`. `presentation/ports.py`'s `ChannelReadinessRefusal`
    is the `Enum` an embedder matches on, and `presentation/api.py` translates the
    two by value -- exactly the split `ProcessUnknown` already has between
    `infra/processes.py`'s own dataclass and `presentation/ports.py`'s.
    """

    reason: str


PEER_OUTSIDE_JAIL = "peer_outside_jail"
"""The peer connected, and its own `/proc/<pid>/ns/pid` is not the jail's namespace
-- decision-0005 item 2's strict equality, so a listener in a namespace *nested*
under the jail's is refused too, not accepted.
"""

PEER_LOOKUP_FAILED = "peer_lookup_failed"
"""The peer connected, but its identity could not be established: any `OSError` out
of `SO_PEERPIDFD`, the `ns/pid` readlink or the pidfd re-check (decision-0005 item
5), and also the pid-mismatch case where the two reads disagree -- a pid reused
between them, refused rather than resolved.
"""

KERNEL_UNSUPPORTED = "kernel_unsupported"
"""This kernel cannot identify a connected peer at all: `SOL_SOCKET` has no
`SO_PEERPIDFD` (Linux before 6.5), so readiness refuses rather than falling back to
the bare `SO_PEERCRED` pid, which names the `listen()` caller but is not
re-checkable and so reopens the pid-reuse window (decision-0005 item 6).
"""


def _children(pid: int, proc_root: str = "/proc") -> list[int]:
    """`pid`'s direct children, found by scanning every numeric entry of `proc_root`
    and reading its `PPid` line (TASK-0001.24's probe, verbatim).

    A scan, not `/proc/<pid>/task/*/children`: that file names children only for a
    process that is itself this process's child, and it is one of decision-0005's
    own listed, still-unmeasured alternatives. Entries that vanish mid-scan (a
    process can exit between the `listdir` and the read) are skipped, never fatal.

    `proc_root` defaults to the real `/proc` for every production caller; a test
    pointing it at a directory of its own construction is how the scan is exercised
    without a real bwrap jail underneath it.
    """
    found: list[int] = []
    for entry in os.listdir(proc_root):
        if not entry.isdigit():
            continue
        try:
            with open(f"{proc_root}/{entry}/status") as handle:
                for line in handle:
                    if line.startswith("PPid:") and int(line.split()[1]) == pid:
                        found.append(int(entry))
                        break
        except OSError:
            continue
    return found


def _nspid(pid: int, proc_root: str = "/proc") -> str:
    """The `NSpid` line of `/proc/<pid>/status`: the process's pid in every PID
    namespace on the path from the host's down to its own, outermost first.

    Deliberately left uncaught, so every caller states what it does with each
    failure rather than inheriting a decision from here: an `OSError` (the entry
    could not be read -- the process exited mid-scan, or its `/proc` entry is not
    readable by this uid) and a `StopIteration` (`status` carried no `NSpid:` line
    at all) both mean "this candidate is not the jail's PID 1", never "the scan is
    over".
    """
    with open(f"{proc_root}/{pid}/status") as handle:
        return next(line.split(":", 1)[1].strip() for line in handle if line.startswith("NSpid:"))


def _gone(pid: int, proc_root: str = "/proc") -> bool:
    """Whether `pid` has exited: no `/proc` entry for it, or one whose `State:` is
    zombie (`Z`) -- a child of this process stays one until it is reaped, and a jail's
    outer process is exactly that. Any other failure to read it (a permission error,
    say) is *not* evidence it is gone, so it reads as still running.
    """
    try:
        with open(f"{proc_root}/{pid}/status") as handle:
            return any(line.startswith("State:") and line.split()[1] == "Z" for line in handle)
    except FileNotFoundError:
        return True
    except OSError:
        return False


def jail_pid1_namespace(
    bwrap_pid: int,
    deadline: float,
    proc_root: str = "/proc",
) -> int | JailPid1NotFound | JailPid1Exited:
    """Find the jail's own PID namespace -- the one its in-jail PID 1 lives in -- and
    hand back an open fd on it, or `JailPid1NotFound` once `deadline` passes first,
    or `JailPid1Exited` as soon as `bwrap_pid` itself is gone with no PID 1 found.

    `bwrap_pid` is the *outer* bwrap process, which is what `create_bwrap_jail`
    already tracks as `Jail.process.pid` (`infra.processes.spawn` exec'd
    `supervisor_argv[0]`, "bwrap"). It is **not** the in-jail PID 1: TASK-0001.24
    measured both on the same run, and bwrap's own `/proc/<pid>/ns/pid` is the
    *host's* namespace -- `bwrap=9 ns=pid:[4026532557]`, the probe host's own --
    while the in-jail PID 1 is a different host pid entirely, in a different
    namespace (`host_pid=10 NSpid='10\t1' ns=pid:[pid:]`), found by scanning bwrap's
    own `/proc` children for one whose `NSpid` ends in `1` (`--as-pid-1` makes the
    jailed program PID 1 *inside* the new namespace; bwrap still forks once to get
    there, on every run measured). Comparing a peer against bwrap's own namespace
    instead would compare the host namespace with itself and read every peer as
    inside the jail -- the one mistake that makes this whole mechanism hollow while
    every happy-path test still passes.

    The fd this returns is held open by the caller for the jail's whole lifetime,
    never read from: decision-0005 item 1 keeps an fd on the namespace precisely so
    the nsfs inode cannot be recycled while a later readiness check compares against
    it. `os.open`, not `os.readlink`, for that reason -- the caller holds the inode,
    not a string.

    A single candidate whose own `/proc` entries cannot be read (it exited between
    the scan and the read, or its `ns/pid` is not readable by this uid) is skipped;
    an `OSError` from `_children` listing `proc_root` at all (no procfs, or no
    permission on it) propagates, since nothing about the jail can be learned then.

    `JailPid1Exited` (TASK-0001.30): a candidate is looked for *before* `bwrap_pid`
    is checked, on every pass, and never the other way round. A PID 1 that exists
    when the scan runs is therefore always found; one that is not found, with
    `bwrap_pid` gone by the time of the check, can only be a jail whose whole
    command finished first -- bwrap outlives its in-jail PID 1 and never the
    reverse, so there is no PID 1 left to wait for, and no reason to wait out
    `deadline` for one.
    """
    while True:
        for child in _children(bwrap_pid, proc_root):
            try:
                if _nspid(child, proc_root).split()[-1] != "1":
                    continue
                return os.open(f"{proc_root}/{child}/ns/pid", os.O_RDONLY)
            except OSError:
                continue
        if _gone(bwrap_pid, proc_root):
            return JailPid1Exited()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return JailPid1NotFound()
        time.sleep(min(_POLL_INTERVAL_S, remaining))


def channel_ready(
    path: str, jail_namespace_fd: int, *, so_peerpidfd: int = SO_PEERPIDFD
) -> ChannelReady | ChannelNotReady | ChannelRefused:
    """Connect to `path` once, and verify that the process which called `listen()` on
    the socket that answered is inside the jail's own PID namespace -- the namespace
    `jail_namespace_fd`, an open fd on `/proc/<in-jail pid 1>/ns/pid`, names
    (decision-0005 items 1 and 2).

    `so_peerpidfd` defaults to this module's own `SO_PEERPIDFD` -- every production
    call gets the real one. A test overriding it is this function's one seam for
    AC#5 (TASK-0001.27, reworded 2026-10-25): a socket option number no real kernel
    defines makes `getsockopt` fail exactly the way a genuine pre-6.5 kernel's
    missing `SO_PEERPIDFD` would, deterministically, without patching anything
    (determinism as data, not by patching -- this repo's own Python rule). That
    failure is indistinguishable from the real thing *inside this function*: either
    way, the one `getsockopt` call below raises `OSError`, and the refusal it
    produces is the same.

    Adapted from TASK-0001.24's own `verified_ready`, with the two gaps decision-0005
    names closed, and in this order:

    - `connect` raising is `ChannelNotReady`, whatever the `OSError` was: with no
      connection there is no peer to say anything about, and `ENOENT` (nothing at the
      path yet), `ECONNREFUSED` (a socket with no listener) and everything else alike
      are states a later poll can find changed.
    - `SO_PEERPIDFD` is read inside its own `try` -- the probe let this error escape,
      and both skeptics measured it: a `listen()` caller that exited and was reaped
      while its child kept the socket makes `getsockopt` raise `EINVAL`.
    - `/proc/<pid>/ns/pid` is read with the pid the kernel just recorded, and the
      pidfd's own `fdinfo` `Pid:` is re-read straight after, so a pid reused in
      between cannot pass: the two must agree *and* the namespace must equal the
      jail's.

    `SO_PEERPIDFD` itself never raises `AttributeError` here, deliberately: the
    module-level fallback (`getattr(socket, "SO_PEERPIDFD", 77)`, above) already
    resolved the name once, at import time, so this function only ever sees a plain
    int, never a fresh attribute lookup that could fail -- a kernel genuinely
    without `SO_PEERPIDFD` (Linux before 6.5) fails here at *call* time instead,
    with `OSError`/`ENOPROTOOPT`, since the number is a kernel ABI constant and the
    call is what actually asks the kernel.

    `ENOPROTOOPT` specifically -- "this kernel has never heard of this option
    number at all" -- is the *only* `OSError` this call reads as
    `KERNEL_UNSUPPORTED`. Every other one (measured: `EINVAL`, from a kernel that
    does support the option but cannot answer it for *this* peer -- a `listen()`
    caller that exited and was reaped while its child kept the socket, both of
    TASK-0001.24's skeptics measured it) is `PEER_LOOKUP_FAILED` instead: the
    option exists and the kernel tried to use it, it is this one connection's peer
    that could not be identified, which `KERNEL_UNSUPPORTED` would misname as a
    host-wide fact rather than the one-connection fact it actually is. Neither
    ever falls back to `SO_PEERCRED` alone.

    Every failure this function can reach is one of those three values, never a
    raise (decision-0005 item 5) -- with one exception that is the caller's own
    precondition rather than a failure of the check: an `OSError` from the readlink
    opening this function on a `jail_namespace_fd` that is not open (it comes from
    `jail_pid1_namespace`, and is closed exactly once, by `destroy_jail`). That
    readlink is deliberately the *last* thing this function reads, not the first
    (moved here for AC#5's reworked test): every refusal above it -- not-ready,
    peer-lookup-failed, kernel-unsupported -- returns without ever touching
    `jail_namespace_fd` or `/proc/self/fd/` at all, so `so_peerpidfd`'s seam can
    prove the `KERNEL_UNSUPPORTED` path on a host with no real `/proc` namespaces
    to compare against in the first place.
    """
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        try:
            connection.connect(path)
        except OSError:
            return ChannelNotReady()
        try:
            peer_pid, _uid, _gid = struct.unpack(
                "3i",
                connection.getsockopt(
                    socket.SOL_SOCKET,
                    getattr(socket, "SO_PEERCRED", 17),
                    12,
                ),
            )
        except OSError:
            return ChannelRefused(PEER_LOOKUP_FAILED)
        try:
            pidfd = connection.getsockopt(socket.SOL_SOCKET, so_peerpidfd)
        except OSError as exc:
            if exc.errno == errno.ENOPROTOOPT:
                return ChannelRefused(KERNEL_UNSUPPORTED)
            return ChannelRefused(PEER_LOOKUP_FAILED)
        try:
            peer_namespace = os.readlink(f"/proc/{peer_pid}/ns/pid")
            # Pin the pid read just above to the very process the kernel recorded for
            # this connection: if that process exited and its pid was reused in the
            # window, the pidfd's own fdinfo no longer names it (decision-0005 item
            # 1's "re-checks the pidfd so a reused pid cannot pass").
            with open(f"/proc/self/fdinfo/{pidfd}") as handle:
                pidfd_pid = next(int(line.split()[1]) for line in handle if line.startswith("Pid:"))
        except OSError:
            return ChannelRefused(PEER_LOOKUP_FAILED)
        finally:
            os.close(pidfd)
        if pidfd_pid != peer_pid:
            return ChannelRefused(PEER_LOOKUP_FAILED)
        jail_namespace = os.readlink(f"/proc/self/fd/{jail_namespace_fd}")
        if peer_namespace != jail_namespace:
            return ChannelRefused(PEER_OUTSIDE_JAIL)
        return ChannelReady()
    finally:
        connection.close()


def create(path: str) -> None:
    """Make `path` exist, private to the owning user (mode 0o700), and every missing
    parent of it.

    Idempotent: a no-op on a path that already exists, except that its own mode is
    always reset to 0o700 -- a repeated call stays "private to the owning user" even
    should something else have widened it in between.
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(stat.S_IRWXU)


def remove(path: str) -> None:
    """Remove `path` and everything written inside it.

    `shutil.rmtree`'s own `FileNotFoundError` (or any other `OSError`) propagates:
    a caller that treats an already-gone directory as fine (every caller in this
    codebase so far) catches it itself, the same way it already does for the
    supervisor script's own `unlink`.
    """
    shutil.rmtree(path)
