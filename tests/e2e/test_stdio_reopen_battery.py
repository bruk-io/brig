"""TASK-0042: a jail reopens its own stdio through `/proc/self/fd` with a wider mode than brig
opened it with, against real bwrap.

The magic link reopens whatever the fd is. Handed an fd on a host file, a jail with no writable
root truncates the embedder's stdin file, reads the earlier contents of a file it was only to
append to, and truncates that file: permission is checked on the file's mode for the same uid,
not on the mode brig opened it with. Handed a pipe, it reaches only the pipe. Each case has a
positive control: the stream still carries what it should.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from brig import Stdio, create_bwrap_jail, destroy_jail, run_jail

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_REOPEN = """
import os, sys
received = sys.stdin.read()
try:
    reopened = os.open("/proc/self/fd/1", os.O_RDONLY | os.O_NONBLOCK)
    seen = os.read(reopened, 4096)
except OSError:
    seen = b""
leaked = b"EARLIER" in seen
for number in (0, 2):
    try:
        fd = os.open(f"/proc/self/fd/{number}", os.O_WRONLY | os.O_TRUNC)
        os.write(fd, b"JAIL")
        os.close(fd)
    except OSError:
        pass
os.write(1, ("control|" + received).encode())
sys.exit(9 if leaked else 0)
"""
"""Read stdin (the control: its bytes arrive), then reopen fd 1 for reading and fd 0 and fd 2
for writing with truncation. Exit 9 when fd 1's reopening read what the file held before the
jail started."""


def test_reopening_path_stdio_reaches_none_of_the_host_files() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as streams:
        stdin, stdout, stderr = (Path(streams) / name for name in ("in", "out", "err"))
        stdin.write_text("the host's input")
        stdout.write_text("EARLIER output\n")
        stderr.write_text("EARLIER log\n")
        jail = create_bwrap_jail(
            (sys.executable, "-I", "-c", _REOPEN),
            stdio=Stdio(stdin=str(stdin), stdout=str(stdout), stderr=str(stderr)),
        )
        try:
            code = run_jail(jail, timeout_s=15)
        finally:
            destroy_jail(jail)
        out, err, kept_in = stdout.read_text(), stderr.read_text(), stdin.read_text()
    assert "control|the host's input" in out, f"the control did not get through: {out!r}"
    assert code != 9, "the jail read the stdout file's earlier contents through /proc/self/fd/1"
    assert kept_in == "the host's input", f"the jail rewrote the stdin file: {kept_in!r}"
    assert out.startswith("EARLIER output\n"), f"the jail truncated the stdout file: {out!r}"
    assert err.startswith("EARLIER log\n"), f"the jail truncated the stderr file: {err!r}"


_EMBEDDER = """
import sys
from brig import create_bwrap_jail, destroy_jail, run_jail
jail = create_bwrap_jail((sys.executable, "-I", "-c", sys.argv[1]))
try:
    code = run_jail(jail, timeout_s=15)
finally:
    destroy_jail(jail)
sys.exit(code)
"""
"""An embedder whose own stdout and stderr are its log files, running the probe with the
default stdio: its own streams."""


def test_reopening_inherited_stdio_reaches_none_of_the_embedders_files() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as streams:
        stdout, stderr = Path(streams) / "out", Path(streams) / "err"
        stdout.write_text("EARLIER output\n")
        stderr.write_text("EARLIER log\n")
        with stdout.open("a") as out_file, stderr.open("a") as err_file:
            embedder = subprocess.run(
                (sys.executable, "-c", _EMBEDDER, _REOPEN),
                stdin=subprocess.DEVNULL,
                stdout=out_file,
                stderr=err_file,
                timeout=60,
            )
        out, err = stdout.read_text(), stderr.read_text()
    assert "control|" in out, f"the control did not get through: {out!r} {err!r}"
    assert embedder.returncode != 9, "the jail read the embedder's stdout file through its fd"
    assert out.startswith("EARLIER output\n"), f"the jail truncated the embedder's file: {out!r}"
    assert err.startswith("EARLIER log\n"), f"the jail truncated the embedder's log: {err!r}"
