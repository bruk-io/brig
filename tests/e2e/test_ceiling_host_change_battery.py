"""TASK-0043: three ceilings a jail's report stated as `ENFORCED` where only a list of places
backed them, each planted against a real jail.

Each case is a violation the host takes part in: it replaces a directory a readable root nested
in a writable one is mounted on, or keeps a listening socket in a place the jail can see that no
list names. `BEST_EFFORT` is the grade that allows for the host changing what the jail sees
(decision-0008), so the report is held to this: with the violation blocked, any grade; with it
through, nothing stronger than `BEST_EFFORT`. A positive control beside each shows the probe
could see the violation at all.
"""

import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from brig import (
    CHANNEL_EXCLUSIVITY_CLAIM,
    FS_WRITE_CLAIM,
    NETWORK_CLAIM,
    Claim,
    FsPolicy,
    Grade,
    Jail,
    at_most,
    create_bwrap_jail,
    destroy_jail,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_LISTED_PLACES = ("/run", "/var/run", "/tmp", "/var/tmp", "/dev/shm")
"""The socket places decision-0008 item 5 lists; the planted socket must lie outside them."""


def _held_under_host_change(jail: Jail, claim: Claim, *, control: bool, blocked: bool) -> None:
    """The report for `claim` allows for what was measured with the host's help: anything when
    the violation was blocked, at most `BEST_EFFORT` when it got through."""
    assert control, f"{claim.name}: the positive control failed, so the probe proves nothing"
    allowed = Grade.ENFORCED if blocked else Grade.BEST_EFFORT
    assert at_most(jail.report[claim], allowed), (claim.name, jail.report[claim], allowed)


def _narrow(*extra: str) -> FsPolicy:
    """Readable roots for the interpreter and the system, none of them a listed socket place,
    plus `extra`."""
    system = (
        "/usr",
        "/bin",
        "/lib",
        "/lib64",
        "/etc",
        sys.prefix,
        str(Path(sys.base_prefix).parent),
    )
    return FsPolicy(readable=(*(p for p in system if Path(p).exists()), *extra))


def _outside_the_listed_places() -> tempfile.TemporaryDirectory[str]:
    """A fresh directory under the home directory, as an agent's socket directory is."""
    home = str(Path.home())
    if any(home == place or home.startswith(place + "/") for place in _LISTED_PLACES):
        pytest.skip(f"the home directory {home} is inside a listed socket place")
    return tempfile.TemporaryDirectory(dir=home, prefix=".brig-")


_WRITE_AFTER_GO = (
    "import os, sys, time\n"
    "root, go = sys.argv[1:3]\n"
    "open(root + '/beside', 'w').write('x')\n"
    "while not os.path.exists(go):\n"
    "    time.sleep(0.02)\n"
    "try:\n"
    "    open(root + '/vendor/lib.py', 'w').write('JAIL')\n"
    "except OSError:\n"
    "    sys.exit(7)\n"
)


def test_fs_write_the_host_replacing_a_nested_readable_root_lets_the_jail_write_into_it() -> None:
    """A readable root `W/vendor` inside the writable root `W`. The host renames `W/vendor` away
    (its mount moves with the entry) and makes a new `W/vendor`; the jail then writes
    `W/vendor/lib.py` through `W`'s writable mount."""
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as root,
        tempfile.TemporaryDirectory(dir="/tmp") as side,
    ):
        vendor = Path(root) / "vendor"
        vendor.mkdir()
        (vendor / "lib.py").write_text("the host's")
        go = Path(side) / "go"
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _WRITE_AFTER_GO, root, str(go)),
            policy=FsPolicy(readable=("/", str(vendor)), writable=(root,)),
        )
        try:
            _wait_for(Path(root) / "beside")  # the jail's mounts are in place
            os.rename(vendor, Path(root) / "vendor.old")
            vendor.mkdir()
            go.write_text("")
            code = run_jail(jail, timeout_s=15)
        finally:
            destroy_jail(jail)
        control = (Path(root) / "beside").exists()
        written = (vendor / "lib.py").exists()
    _held_under_host_change(
        jail, FS_WRITE_CLAIM, control=control, blocked=code == 7 and not written
    )


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 10
    while not path.exists():
        assert time.monotonic() < deadline, f"the jail never wrote {path}"
        time.sleep(0.02)


_DIAL = (
    "import socket, sys\n"
    "client = socket.socket(socket.AF_UNIX)\n"
    "try:\n"
    "    client.connect(sys.argv[1])\n"
    "    client.sendall(b'ping')\n"
    "    client.close()\n"
    "except OSError:\n"
    "    sys.exit(7)\n"
)


def test_channel_exclusivity_a_host_socket_outside_the_listed_places_is_dialled() -> None:
    """An agent's socket under the home directory, which no list of socket places names, inside
    a readable root: the jail dials it. The control: the host itself reaches it."""
    with _outside_the_listed_places() as place:
        path = f"{place}/agent.sock"
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(path)
            listener.listen()
            with socket.socket(socket.AF_UNIX) as host:
                host.connect(path)
            code, jail = _run(_DIAL, path, policy=_narrow(place))
    _held_under_host_change(jail, CHANNEL_EXCLUSIVITY_CLAIM, control=True, blocked=code == 7)


def _relay(listener: socket.socket, port: int, stop: threading.Event) -> None:
    """Accept on `listener` and carry what arrives to `127.0.0.1:port`: what a host agent that
    reaches the network does for whoever dials it."""
    listener.settimeout(0.2)
    while not stop.is_set():
        try:
            accepted, _ = listener.accept()
        except TimeoutError:
            continue
        with accepted, socket.create_connection(("127.0.0.1", port), timeout=5) as onward:
            accepted.settimeout(5)
            while data := accepted.recv(4096):
                onward.sendall(data)


def test_network_a_dialable_host_socket_carries_the_network() -> None:
    """The jail has no network interface of its own, but a host socket it can dial relays to a
    TCP listener: the jail's bytes reach the network. The control: the host reaches the TCP
    listener itself."""
    with (
        _outside_the_listed_places() as place,
        socket.socket() as server,
        socket.socket(socket.AF_UNIX) as relay,
    ):
        server.bind(("127.0.0.1", 0))
        server.listen()
        server.settimeout(10)
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            control_peer, _ = server.accept()
            control_peer.close()
        path = f"{place}/agent.sock"
        relay.bind(path)
        relay.listen()
        stop = threading.Event()
        relaying = threading.Thread(target=_relay, args=(relay, port, stop), daemon=True)
        relaying.start()
        try:
            _, jail = _run(_DIAL, path, policy=_narrow(place))
            try:
                peer, _ = server.accept()
                with peer:
                    peer.settimeout(5)
                    reached = peer.recv(4) == b"ping"
            except TimeoutError:
                reached = False
        finally:
            stop.set()
            relaying.join(timeout=5)
    _held_under_host_change(jail, NETWORK_CLAIM, control=True, blocked=not reached)


def _run(program: str, *argv: str, policy: FsPolicy) -> tuple[int, Jail]:
    jail = create_bwrap_jail((sys.executable, "-I", "-c", program, *argv), policy=policy)
    try:
        return run_jail(jail, timeout_s=15), jail
    finally:
        destroy_jail(jail)
