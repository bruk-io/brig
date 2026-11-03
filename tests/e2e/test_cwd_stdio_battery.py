"""TASK-0028: an embedder sets the jailed command's working directory and its stdio, through
the public API, against real bwrap. The command reports through the streams under test."""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from brig import FsPolicy, PolicyCwdOutsideRoots, Stdio, create_bwrap_jail, destroy_jail, run_jail

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_REPORTER = """
import os, sys
sys.stdout.write(os.getcwd() + "|" + sys.stdin.read())
sys.stdout.flush()
sys.stderr.write("to stderr")
"""


def _run(command: tuple[str, ...], **kwargs: object) -> int:
    jail = create_bwrap_jail(command, **kwargs)  # type: ignore[arg-type]
    try:
        return run_jail(jail, timeout_s=15)
    finally:
        destroy_jail(jail)


def test_the_command_starts_in_cwd_and_its_streams_go_where_stdio_says() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as root:
        work = Path(root) / "work"
        work.mkdir()
        stdin = Path(root) / "in.txt"
        stdin.write_text("from stdin")
        out, err = Path(root) / "out.txt", Path(root) / "err.txt"
        exit_code = _run(
            (sys.executable, "-I", "-c", _REPORTER),
            policy=FsPolicy(readable=("/",), writable=(root,)),
            cwd=str(work),
            stdio=Stdio(stdin=str(stdin), stdout=str(out), stderr=str(err)),
        )
        assert exit_code == 0
        assert out.read_text() == f"{work}|from stdin"
        assert err.read_text() == "to stderr"
        assert out.stat().st_mode & 0o777 == 0o600


def test_a_stream_sent_to_dev_null_is_discarded_and_others_stay_the_embedders(
    capfd: pytest.CaptureFixture[str],
) -> None:
    exit_code = _run(
        (sys.executable, "-I", "-c", "import sys; print('kept'); sys.stderr.write('dropped')"),
        stdio=Stdio(stderr="/dev/null"),
    )
    captured = capfd.readouterr()
    assert exit_code == 0
    assert "kept" in captured.out
    assert "dropped" not in captured.err


def test_a_cwd_outside_every_root_is_refused_before_anything_starts() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as root:
        with pytest.raises(PolicyCwdOutsideRoots):
            create_bwrap_jail(
                (sys.executable, "-c", "pass"), policy=FsPolicy(readable=("/usr",)), cwd=root
            )
