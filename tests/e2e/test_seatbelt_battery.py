"""TASK-0061, decision-0008 and decision-0010: each claim a Seatbelt jail's report states, held
to what this battery measures on a Mac against the real `/usr/bin/sandbox-exec`.

Every attack runs twice: once unjailed, as the control that shows the probe can do it at all on
this host, and once in a jail, where it must be refused. Each probe is a small Python program
that exits 0 when the attack worked and 7 when the kernel refused it (`EPERM` or `EACCES`); any
other exit is a broken probe, never read as a refusal. The jail's own report is held to the
grade the evidence earns (`at_most`).
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from brig import (
    SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM,
    SEATBELT_FS_READ_CLAIM,
    SEATBELT_FS_WRITE_CLAIM,
    SEATBELT_NETWORK_CLAIM,
    WHOLE_HOST_READ_ONLY,
    Claim,
    Evidence,
    FsPolicy,
    Grade,
    Jail,
    at_most,
    create_seatbelt_jail,
    destroy_jail,
    grade,
    run_jail,
)
from brig.infra import files

pytestmark = pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").exists(),
    reason="sandbox-exec is Darwin's; test skips on Linux, runs on a Mac",
)

_WORKED = 0
_REFUSED = 7

_PRELUDE = (
    "import errno, os, socket, sys\n"
    "def refused(error):\n"
    "    sys.exit(7 if error.errno in (errno.EPERM, errno.EACCES) else 3)\n"
)
"""Every probe starts with this: `refused(error)` exits 7 for the kernel's refusal and 3 for any
other error, so a probe that broke never passes as one that was refused."""


def _python(program: str, *argv: str) -> tuple[str, ...]:
    return (sys.executable, "-I", "-c", _PRELUDE + program, *argv)


def _unjailed(program: str, *argv: str) -> int:
    return subprocess.run(_python(program, *argv), check=False, timeout=30).returncode


def _jailed(program: str, *argv: str, policy: FsPolicy = WHOLE_HOST_READ_ONLY) -> tuple[int, Jail]:
    jail = create_seatbelt_jail(_python(program, *argv), policy=policy)
    try:
        return run_jail(jail, timeout_s=30), jail
    finally:
        destroy_jail(jail)


def _interpreter_roots() -> tuple[str, ...]:
    """Readable roots that reach this interpreter: the directory of each link on the way to it
    and its install's prefix, as `interpreter_refusal` asks of a policy that reads less than
    the whole host."""
    chain = files.link_chain(sys.executable)
    prefix = str(Path(os.path.realpath(sys.executable)).parent.parent)
    venv = str(Path(sys.executable).parent.parent)
    return tuple(dict.fromkeys((*(str(Path(link).parent) for link in chain), prefix, venv)))


def _held_to(jail: Jail, claim: Claim, control: bool, blocked: bool) -> None:
    measured = grade(
        (claim,), {claim: Evidence(control_observed=control, violation_blocked=blocked)}
    )
    assert at_most(jail.report[claim], measured[claim]), (claim.name, jail.report[claim], measured)


@pytest.fixture
def short_dir() -> Iterator[Path]:
    """A directory with a path short enough for an `AF_UNIX` socket (104 bytes on Darwin),
    which pytest's own `tmp_path` is not."""
    made = Path(tempfile.mkdtemp(prefix="brig-", dir="/private/tmp"))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


_WRITE = (
    "try:\n"
    "    with open(sys.argv[1], 'w') as handle:\n"
    "        handle.write('written')\n"
    "except OSError as error:\n"
    "    refused(error)\n"
)


def test_a_write_outside_the_project_is_refused(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    policy = FsPolicy(readable=("/",), writable=(str(project),))

    control = _unjailed(_WRITE, str(outside / "control"))
    inside, _ = _jailed(_WRITE, str(project / "inside"), policy=policy)
    attack, jail = _jailed(_WRITE, str(outside / "attack"), policy=policy)

    assert control == _WORKED and (outside / "control").exists()
    assert inside == _WORKED and (project / "inside").exists()
    assert attack == _REFUSED
    assert not (outside / "attack").exists()
    assert jail.report[SEATBELT_FS_WRITE_CLAIM] is Grade.ENFORCED
    _held_to(jail, SEATBELT_FS_WRITE_CLAIM, control=inside == _WORKED, blocked=attack == _REFUSED)


_LINK = (
    "try:\n    os.link(sys.argv[1], sys.argv[2])\nexcept OSError as error:\n    refused(error)\n"
)


def test_a_hard_link_to_a_file_outside_the_project_is_refused(tmp_path: Path) -> None:
    """A link in the project to a read-only file would be a second, writable name for it."""
    project = tmp_path / "project"
    project.mkdir()
    target = tmp_path / "read-only.txt"
    target.write_text("host's")
    policy = FsPolicy(readable=("/",), writable=(str(project),))

    control = _unjailed(_LINK, str(target), str(tmp_path / "control-link"))
    attack, jail = _jailed(_LINK, str(target), str(project / "link"), policy=policy)

    assert control == _WORKED
    assert attack == _REFUSED
    assert not (project / "link").exists()
    _held_to(jail, SEATBELT_FS_WRITE_CLAIM, control=control == _WORKED, blocked=True)


_CARRY_AWAY = (
    "root, deny = sys.argv[1], sys.argv[2]\n"
    "try:\n"
    "    os.rename(root + '/a', root + '/moved')\n"
    "    with open(root + '/moved/b/deny/planted', 'w') as handle:\n"
    "        handle.write('planted')\n"
    "    os.rename(root + '/moved', root + '/a')\n"
    "except OSError as error:\n"
    "    refused(error)\n"
)


def test_a_directory_on_the_way_to_a_write_deny_cannot_be_renamed_away(tmp_path: Path) -> None:
    """old SPEC decision-207: a rename is judged by its paths, so without a pin the command
    renames the directory above a deny, writes beneath the new name, and renames it back."""
    for root in ("control", "project"):
        (tmp_path / root / "a" / "b" / "deny").mkdir(parents=True)
    project = tmp_path / "project"
    deny = project / "a" / "b" / "deny"
    policy = FsPolicy(readable=("/",), writable=(str(project),), write_denies=(str(deny),))

    control = _unjailed(_CARRY_AWAY, str(tmp_path / "control"), "")
    attack, jail = _jailed(_CARRY_AWAY, str(project), str(deny), policy=policy)
    direct, _ = _jailed(_WRITE, str(deny / "direct"), policy=policy)

    assert control == _WORKED
    assert (tmp_path / "control" / "a" / "b" / "deny" / "planted").exists()
    assert attack == _REFUSED
    assert direct == _REFUSED
    assert not (deny / "planted").exists() and not (deny / "direct").exists()
    assert (project / "a").is_dir() and not (project / "moved").exists()
    _held_to(jail, SEATBELT_FS_WRITE_CLAIM, control=control == _WORKED, blocked=True)


_READ = (
    "try:\n"
    "    with open(sys.argv[1]) as handle:\n"
    "        handle.read()\n"
    "except OSError as error:\n"
    "    refused(error)\n"
)


def test_a_masked_secret_cannot_be_read(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "readme").write_text("public")
    secret = project / "secret.env"
    secret.write_text("TOKEN=hunter2")
    policy = FsPolicy(readable=("/",), writable=(str(project),), masks=(str(secret),))

    control = _unjailed(_READ, str(secret))
    sibling, _ = _jailed(_READ, str(project / "readme"), policy=policy)
    attack, jail = _jailed(_READ, str(secret), policy=policy)

    assert control == _WORKED
    assert sibling == _WORKED
    assert attack == _REFUSED
    _held_to(jail, SEATBELT_FS_READ_CLAIM, control=sibling == _WORKED, blocked=True)


def test_a_file_outside_every_readable_root_cannot_be_read(tmp_path: Path) -> None:
    readable = tmp_path / "readable"
    readable.mkdir()
    (readable / "inside").write_text("inside")
    outside = tmp_path / "outside"
    outside.write_text("outside")
    policy = FsPolicy(readable=(str(readable), *_interpreter_roots()))

    control = _unjailed(_READ, str(outside))
    inside, _ = _jailed(_READ, str(readable / "inside"), policy=policy)
    attack, jail = _jailed(_READ, str(outside), policy=policy)

    assert control == _WORKED
    assert inside == _WORKED
    assert attack == _REFUSED
    _held_to(jail, SEATBELT_FS_READ_CLAIM, control=inside == _WORKED, blocked=True)


def test_the_reasons_reads_are_only_best_effort_are_real(tmp_path: Path) -> None:
    """What `SEATBELT_FS_READ_CLAIM` names as host data the jail sees whatever its policy: the
    names at `/`, and a host process's arguments through `sysctl`. Measured, so the report's
    `BEST_EFFORT` is not stated weaker than it needs to be without a reason."""
    readable = tmp_path / "readable"
    readable.mkdir()
    policy = FsPolicy(readable=(str(readable), *_interpreter_roots()))
    host = subprocess.Popen(["/bin/sleep", "30"])
    program = (
        "import ctypes\n"
        "names = os.listdir('/')\n"
        "libc = ctypes.CDLL(None)\n"
        "mib = (ctypes.c_int * 3)(1, 49, int(sys.argv[1]))\n"
        "size = ctypes.c_size_t(65536)\n"
        "buf = ctypes.create_string_buffer(65536)\n"
        "if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:\n"
        "    sys.exit(7)\n"
        "sys.exit(0 if 'Users' in names and b'/bin/sleep' in buf.raw[: size.value] else 3)\n"
    )
    try:
        seen, jail = _jailed(program, str(host.pid), policy=policy)
    finally:
        host.kill()
        host.wait()

    assert seen == _WORKED
    assert jail.report[SEATBELT_FS_READ_CLAIM] is Grade.BEST_EFFORT


_DIAL_TCP = (
    "try:\n"
    "    socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=5).close()\n"
    "except OSError as error:\n"
    "    refused(error)\n"
)


def test_no_tcp_connection_leaves_the_jail() -> None:
    accepted: list[object] = []
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = str(listener.getsockname()[1])
        listener.settimeout(0.2)

        def accept() -> None:
            while True:
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                accepted.append(connection)
                connection.close()

        threading.Thread(target=accept, daemon=True).start()
        control = _unjailed(_DIAL_TCP, port)
        reached = len(accepted)
        attack, jail = _jailed(_DIAL_TCP, port)

    assert control == _WORKED and reached == 1
    assert attack == _REFUSED
    assert len(accepted) == reached
    assert jail.report[SEATBELT_NETWORK_CLAIM] is Grade.ENFORCED
    _held_to(jail, SEATBELT_NETWORK_CLAIM, control=control == _WORKED, blocked=True)


_DIAL_UDP = (
    "try:\n"
    "    socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'x', ('127.0.0.1', "
    "int(sys.argv[1])))\n"
    "except OSError as error:\n"
    "    refused(error)\n"
)


def test_no_udp_datagram_leaves_the_jail() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(2)
        port = str(receiver.getsockname()[1])
        control = _unjailed(_DIAL_UDP, port)
        got_control = receiver.recv(16) == b"x"
        attack, jail = _jailed(_DIAL_UDP, port)

    assert control == _WORKED and got_control
    assert attack == _REFUSED
    _held_to(jail, SEATBELT_NETWORK_CLAIM, control=got_control, blocked=True)


_DIAL_UNIX = (
    "try:\n"
    "    socket.socket(socket.AF_UNIX).connect(sys.argv[1])\n"
    "except OSError as error:\n"
    "    refused(error)\n"
)


def test_a_host_socket_in_a_readable_root_cannot_be_dialled(short_dir: Path) -> None:
    """Unlike a bind mount, Seatbelt refuses the connect itself, wherever the socket sits: why
    reading the whole host does not lower `channel_exclusivity` or `network` here."""
    path = str(short_dir / "host.sock")
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(path)
        listener.listen(8)
        control = _unjailed(_DIAL_UNIX, path)
        attack, jail = _jailed(_DIAL_UNIX, path)

    assert control == _WORKED
    assert attack == _REFUSED
    assert jail.report[SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM] is Grade.ENFORCED
    _held_to(jail, SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM, control=control == _WORKED, blocked=True)
    _held_to(jail, SEATBELT_NETWORK_CLAIM, control=control == _WORKED, blocked=True)


_SIGNAL = (
    "import signal\n"
    "try:\n"
    "    os.kill(int(sys.argv[1]), int(sys.argv[2]))\n"
    "except OSError as error:\n"
    "    refused(error)\n"
)


def test_a_host_process_cannot_be_signalled() -> None:
    host = subprocess.Popen(["/bin/sleep", "60"])
    try:
        control = _unjailed(_SIGNAL, str(host.pid), "0")
        attack, jail = _jailed(_SIGNAL, str(host.pid), str(int(signal.SIGTERM)))
        survived = host.poll() is None
    finally:
        host.kill()
        host.wait()
    own = (
        "import signal, subprocess\n"
        "child = subprocess.Popen(['/bin/sleep', '60'])\n"
        "os.kill(child.pid, signal.SIGTERM)\n"
        "sys.exit(0 if child.wait() == -signal.SIGTERM else 3)\n"
    )
    own_child, _ = _jailed(own)

    assert control == _WORKED
    assert own_child == _WORKED, "control: the jail signals its own processes"
    assert attack == _REFUSED and survived
    _held_to(jail, SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM, control=control == _WORKED, blocked=True)


def test_another_jail_cannot_be_signalled() -> None:
    victim = create_seatbelt_jail(("/bin/sleep", "60"))
    try:
        control = _unjailed(_SIGNAL, str(victim.process.pid), "0")
        attack, jail = _jailed(_SIGNAL, str(victim.process.pid), str(int(signal.SIGKILL)))
        survived = _alive(victim.process.pid)
    finally:
        destroy_jail(victim)

    assert control == _WORKED
    assert attack == _REFUSED and survived
    _held_to(jail, SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM, control=control == _WORKED, blocked=True)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


_LOOK_UP = (
    "import ctypes\n"
    "libc = ctypes.CDLL(None)\n"
    "port = ctypes.c_uint(0)\n"
    "bootstrap = ctypes.c_uint.in_dll(libc, 'bootstrap_port')\n"
    "found = libc.bootstrap_look_up(bootstrap, sys.argv[1].encode(), ctypes.byref(port))\n"
    "sys.exit(0 if found == 0 else 7)\n"
)
"""Look a Mach service up by name through `bootstrap_look_up`: 0 found, 7 refused. Nothing is
sent to the service."""


def test_a_mach_service_but_the_directory_lookups_is_refused() -> None:
    """The pasteboard stands for every service the profile does not name: unfiltered, a jail
    read the host's pasteboard through it (measured, TASK-0061)."""
    service = "com.apple.pasteboard.1"
    control = _unjailed(_LOOK_UP, service)
    lookups, _ = _jailed(_LOOK_UP, "com.apple.system.opendirectoryd.libinfo")
    attack, jail = _jailed(_LOOK_UP, service)
    users, _ = _jailed("import pwd\npwd.getpwuid(os.getuid())\n")

    assert control == _WORKED
    assert lookups == _WORKED and users == _WORKED
    assert attack == _REFUSED
    _held_to(jail, SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM, control=control == _WORKED, blocked=True)
    _held_to(jail, SEATBELT_NETWORK_CLAIM, control=control == _WORKED, blocked=True)


def _own_terminal() -> str | None:
    """A terminal device of this user's that is open to writing, or `None`."""
    for name in sorted(os.listdir("/dev")):
        path = f"/dev/{name}"
        if name.startswith("ttys") and os.stat(path).st_uid == os.getuid():
            if os.access(path, os.W_OK):
                return path
    return None


_OPEN_FOR_WRITE = (
    "try:\n"
    "    os.close(os.open(sys.argv[1], os.O_WRONLY | os.O_NOCTTY))\n"
    "except OSError as error:\n"
    "    refused(error)\n"
)
"""Open a device for writing, and write nothing: the control must not type on a terminal."""


def test_a_terminal_of_the_user_s_cannot_be_opened_for_writing() -> None:
    terminal = _own_terminal()
    if terminal is None:
        pytest.skip("no terminal of this user's is open on this host")
    control = _unjailed(_OPEN_FOR_WRITE, terminal)
    attack, jail = _jailed(_OPEN_FOR_WRITE, terminal)

    assert control == _WORKED
    assert attack == _REFUSED
    _held_to(jail, SEATBELT_FS_WRITE_CLAIM, control=control == _WORKED, blocked=True)
