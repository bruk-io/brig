"""decision-0008: no claim a jail's report states is stronger than what this battery measures.

Each claim's violation is planted against a real jail with a positive control beside it, graded
with `grade` from the evidence, and the jail's own report is held to that (`at_most`). A
regression in a mechanism grades the claim lower here and fails the report's ceiling.
"""

import json
import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

import pytest

from brig import (
    ENV_CLAIM,
    FS_READ_CLAIM,
    FS_WRITE_CLAIM,
    NETWORK_CLAIM,
    NETWORK_EGRESS_CLAIM,
    WHOLE_HOST_READ_ONLY,
    Claim,
    Destination,
    EgressPolicy,
    EnvPolicy,
    Evidence,
    FsPolicy,
    Grade,
    Jail,
    Stdio,
    allow_egress,
    at_most,
    create_bwrap_jail,
    destroy_jail,
    egress_record,
    grade,
    render,
    revoke_egress,
    run_jail,
)

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)


def _exit(program: str, *argv: str, **kwargs: object) -> tuple[int, Jail]:
    jail = create_bwrap_jail((sys.executable, "-I", "-c", program, *argv), **kwargs)  # type: ignore[arg-type]
    try:
        return run_jail(jail, timeout_s=15), jail
    finally:
        destroy_jail(jail)


def _held_to(jail: Jail, claim: Claim, control: bool, blocked: bool) -> None:
    measured = grade(
        (claim,), {claim: Evidence(control_observed=control, violation_blocked=blocked)}
    )
    assert at_most(jail.report[claim], measured[claim]), (claim.name, jail.report[claim], measured)


def test_network_no_connection_leaves_the_jail() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            control = True  # the host itself reaches it
        program = (
            "import socket, sys\n"
            "try:\n"
            "    socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=3)\n"
            "except OSError:\n"
            "    sys.exit(7)\n"
        )
        code, jail = _exit(program, str(port))
    _held_to(jail, NETWORK_CLAIM, control, blocked=code == 7)


def test_fs_write_a_write_outside_the_writable_root_is_refused() -> None:
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as root,
        tempfile.TemporaryDirectory(dir="/tmp") as outside,
    ):
        program = (
            "import sys\n"
            "open(sys.argv[1] + '/inside', 'w').write('x')\n"
            "try:\n"
            "    open(sys.argv[2] + '/outside', 'w').write('x')\n"
            "except OSError:\n"
            "    sys.exit(7)\n"
        )
        code, jail = _exit(
            program, root, outside, policy=FsPolicy(readable=("/",), writable=(root,))
        )
        control = (Path(root) / "inside").exists()
        blocked = code == 7 and not (Path(outside) / "outside").exists()
    _held_to(jail, FS_WRITE_CLAIM, control, blocked)


def test_fs_read_a_masked_file_reads_nothing_of_the_host() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as root:
        secret, plain = Path(root) / "secret", Path(root) / "plain"
        secret.write_text("hunter2")
        plain.write_text("visible")
        program = (
            "import sys\n"
            "assert open(sys.argv[2]).read() == 'visible'\n"
            "try:\n"
            "    leaked = 'hunter2' in open(sys.argv[1]).read()\n"
            "except OSError:\n"
            "    leaked = False\n"
            "sys.exit(9 if leaked else 7)\n"
        )
        code, jail = _exit(
            program, str(secret), str(plain), policy=FsPolicy(readable=("/",), masks=(str(secret),))
        )
    _held_to(jail, FS_READ_CLAIM, control=code in (7, 9), blocked=code == 7)


def test_env_only_the_allowed_variables_reach_the_command() -> None:
    """The candidate environment carries an allowed variable and a secret one; only the allowed
    one reaches the command (the control: it does)."""
    program = (
        "import os, sys\n"
        "control = os.environ.get('BRIG_REPORT_ALLOWED') == 'yes'\n"
        "leaked = 'BRIG_REPORT_SECRET' in os.environ\n"
        "sys.exit((1 if control else 0) + (2 if leaked else 0))\n"
    )
    code, jail = _exit(
        program,
        env={"BRIG_REPORT_ALLOWED": "yes", "BRIG_REPORT_SECRET": "no"},
        env_policy=EnvPolicy(allowed=("BRIG_REPORT_ALLOWED",)),
    )
    _held_to(jail, ENV_CLAIM, control=bool(code & 1), blocked=not code & 2)


def test_a_mask_inside_a_writable_root_is_reported_best_effort() -> None:
    """What the report says when the host could undo a mask: no stronger than best-effort."""
    with tempfile.TemporaryDirectory(dir="/tmp") as root:
        (Path(root) / "secret").write_text("x")
        _, jail = _exit(
            "pass", policy=FsPolicy(readable=("/",), writable=(root,), masks=(f"{root}/secret",))
        )
    assert jail.report[FS_READ_CLAIM] is Grade.BEST_EFFORT
    _, default = _exit("pass", policy=WHOLE_HOST_READ_ONLY)
    assert default.report[FS_READ_CLAIM] is Grade.ENFORCED


_DIAL = (
    "import socket, sys\n"
    "client = socket.socket(socket.AF_UNIX)\n"
    "try:\n"
    "    client.connect(sys.argv[1])\n"
    "except OSError:\n"
    "    sys.exit(7)\n"
)


def test_channel_exclusivity_a_host_socket_in_a_socket_place_is_reached_only_where_it_is_seen() -> (
    None
):
    """decision-0008 item 5: a host listener in `/tmp`. Under the default policy the jail dials
    it (measured VIOLATED; the report says no more); under a policy that shows no socket place it
    cannot (measured ENFORCED). The report there says only BEST_EFFORT (TASK-0043): its readable
    roots are host directories a socket could sit in, and no list of places finds every one
    (`tests/e2e/test_ceiling_host_change_battery.py` dials one). The control: the host itself
    reaches it."""
    from brig import CHANNEL_EXCLUSIVITY_CLAIM

    with tempfile.TemporaryDirectory(dir="/tmp") as place:
        path = f"{place}/host.sock"
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(path)
            listener.listen()
            with socket.socket(socket.AF_UNIX) as host:
                host.connect(path)
            code, wide = _exit(_DIAL, path, policy=WHOLE_HOST_READ_ONLY)
            _held_to(wide, CHANNEL_EXCLUSIVITY_CLAIM, control=True, blocked=code == 7)
            assert code != 7, "the default policy should show /tmp, and so the socket"
            narrow = FsPolicy(
                readable=tuple(
                    p
                    for p in (
                        "/usr",
                        "/bin",
                        "/lib",
                        "/lib64",
                        "/etc",
                        sys.prefix,
                        str(Path(sys.base_prefix).parent),
                    )
                    if Path(p).exists()
                )
            )
            code, jail = _exit(_DIAL, path, policy=narrow)
            _held_to(jail, CHANNEL_EXCLUSIVITY_CLAIM, control=True, blocked=code == 7)
            assert jail.report[CHANNEL_EXCLUSIVITY_CLAIM] is Grade.BEST_EFFORT


_READ_AFTER_GO = (
    "import os, sys, time\n"
    "secret, go = sys.argv[1:3]\n"
    "try:\n"
    "    before = open(secret).read()\n"
    "except OSError:\n"
    "    before = ''\n"
    "while not os.path.exists(go):\n"
    "    time.sleep(0.02)\n"
    "try:\n"
    "    after = open(secret).read()\n"
    "except OSError:\n"
    "    after = ''\n"
    "sys.exit((1 if 'old' in before else 0) + (2 if 'NEW' in after else 0))\n"
)


def test_fs_read_a_mask_the_host_renames_over_is_undone_so_the_report_says_best_effort() -> None:
    """A mask is a mount on the host's directory entry, and the host replacing that entry (an
    editor saving by rename) can detach it in the jail, wherever the mask is: the command alone
    cannot read the secret, and the report says no more than BEST_EFFORT."""
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as root,
        tempfile.TemporaryDirectory(dir="/tmp") as side,
    ):
        secret = Path(root) / "secret"
        secret.write_text("old")
        go = Path(side) / "go"
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _READ_AFTER_GO, str(secret), str(go)),
            policy=FsPolicy(readable=("/",), masks=(str(secret),)),
        )
        try:
            replacement = Path(root) / "secret.new"
            replacement.write_text("NEW")
            os.replace(replacement, secret)
            go.write_text("")
            code = run_jail(jail, timeout_s=15)
        finally:
            destroy_jail(jail)
    assert not code & 1, "the command read the masked secret before the host touched it"
    # Whether the host's rename detaches the mask depends on the kernel and filesystem (an
    # architecture review measured it reading the new file; this container keeps the mask), so
    # the report must allow for it: never ENFORCED for a mask over a host entry.
    assert jail.report[FS_READ_CLAIM] is Grade.BEST_EFFORT


def test_fs_write_a_write_at_a_deny_is_refused_and_a_host_rename_undoes_it() -> None:
    """A write deny inside a writable root refuses the command's write (measured ENFORCED for
    the command alone), and the report says BEST_EFFORT, since the host replacing the denied
    entry detaches its mount."""
    with tempfile.TemporaryDirectory(dir="/tmp") as root:
        hooks = Path(root) / "hooks"
        hooks.mkdir()
        program = (
            "import sys\n"
            "open(sys.argv[1] + '/beside', 'w').write('x')\n"
            "try:\n"
            "    open(sys.argv[1] + '/hooks/pre-commit', 'w').write('x')\n"
            "except OSError:\n"
            "    sys.exit(7)\n"
        )
        code, jail = _exit(
            program,
            root,
            policy=FsPolicy(readable=("/",), writable=(root,), write_denies=(str(hooks),)),
        )
        control = (Path(root) / "beside").exists()
        blocked = code == 7 and not (hooks / "pre-commit").exists()
    _held_to(jail, FS_WRITE_CLAIM, control, blocked)
    assert jail.report[FS_WRITE_CLAIM] is Grade.BEST_EFFORT


_EGRESS_PROBE = r"""
import json, os, socket, sys, time

port, cue = int(sys.argv[1]), sys.argv[2]


def through_the_proxy(name):
    try:
        sock = socket.create_connection(("127.0.0.1", 3128), timeout=10)
        sock.sendall(f"CONNECT {name}:{port} HTTP/1.1\r\n\r\n".encode())
        return sock.recv(64).decode().split("\r\n")[0]
    except OSError as error:
        return type(error).__name__


def direct():
    try:
        socket.create_connection(("127.0.0.1", port), timeout=3)
    except OSError:
        return "refused"
    return "reached"


seen = {
    "granted": through_the_proxy("granted.test"),
    "ungranted": through_the_proxy("elsewhere.test"),
    "direct": direct(),
}
print(json.dumps(seen), flush=True)
while not os.path.exists(cue):
    time.sleep(0.02)
"""
"""The egress claim's probe: a granted name through the proxy (the positive control), an
ungranted one through it and the host's listener dialled directly (the violations), then wait
for the host's cue while it changes the grants."""


def test_network_with_an_egress_policy_reaches_only_what_it_grants_and_the_report_says_so() -> None:
    """decision-0009 item 8: with an `EgressPolicy`, `network` is `NETWORK_EGRESS_CLAIM`, held to
    what this measures, and its text names the CONNECT/SNI and payload gaps. Item 5: the
    rendered report states the policy as created and every change made while the jail ran."""
    with socket.socket() as listener, tempfile.TemporaryDirectory(dir="/tmp") as scratch:
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        port = listener.getsockname()[1]
        out, cue = Path(scratch) / "out", Path(scratch) / "go"
        created = EgressPolicy((Destination("granted.test", port), Destination("127.0.0.1", port)))
        later = Destination("later.test", port)
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _EGRESS_PROBE, str(port), str(cue)),
            egress=created,
            egress_hosts={"granted.test": ("127.0.0.1",), "elsewhere.test": ("127.0.0.1",)},
            stdio=Stdio(stdout=str(out)),
        )
        try:
            deadline = time.monotonic() + 30
            while not (out.exists() and out.read_text().endswith("\n")):
                assert time.monotonic() < deadline, "the probe printed nothing"
                time.sleep(0.02)
            seen = json.loads(out.read_text())
            allow_egress(jail, later)
            revoke_egress(jail, later)
            cue.write_text("")
            assert run_jail(jail, timeout_s=30) == 0
        finally:
            destroy_jail(jail)

    control = seen["granted"] == "HTTP/1.1 200 Connection established"
    blocked = seen["ungranted"] == "HTTP/1.1 403 Forbidden" and seen["direct"] == "refused"
    assert NETWORK_CLAIM not in jail.report
    _held_to(jail, NETWORK_EGRESS_CLAIM, control, blocked)
    text = render(jail.report, egress_record(jail))
    lines = text.splitlines()
    assert (
        f"network: {jail.report[NETWORK_EGRESS_CLAIM]} -- {NETWORK_EGRESS_CLAIM.description}"
        in (lines)
    )
    assert "reaches only the destinations the policy grants, and only through the proxy" in text
    assert "SNI" in text and "not inspected" in text
    assert lines[-4] == f"egress as created: granted.test:{port}, 127.0.0.1:{port}"
    assert lines[-3].startswith(f"egress allow later.test:{port} at ")
    assert lines[-2].startswith(f"egress revoke later.test:{port} at ")
    assert lines[-1] == f"egress now: granted.test:{port}, 127.0.0.1:{port}"
