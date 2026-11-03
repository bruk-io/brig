"""TASK-0028: an embedder sets the jailed command's working directory and its stdio, through
the public API, against real bwrap. The command reports through the streams under test."""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

import brig
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
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as root,
        tempfile.TemporaryDirectory(dir="/tmp") as streams,
    ):
        work = Path(root) / "work"
        work.mkdir()
        stdin = Path(streams) / "in.txt"
        stdin.write_text("from stdin")
        out, err = Path(streams) / "out.txt", Path(streams) / "err.txt"
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


def test_a_stdio_path_inside_a_writable_root_is_refused() -> None:
    """TASK-0031: a jail may write there, so it could swap the file for a link and have the next
    jail's output appended to any file the embedder can write. Refused before anything starts,
    and the file the link points at is untouched."""
    with (
        tempfile.TemporaryDirectory(dir="/tmp") as root,
        tempfile.TemporaryDirectory(dir="/tmp") as elsewhere,
    ):
        victim = Path(elsewhere) / "victim"
        victim.write_text("before")
        (Path(root) / "out.txt").symlink_to(victim)
        refused: Exception | None = None
        try:
            _run(
                (sys.executable, "-I", "-c", "print('appended')"),
                policy=FsPolicy(readable=("/",), writable=(root,)),
                stdio=Stdio(stdout=f"{root}/out.txt"),
            )
        except Exception as error:  # noqa: BLE001 -- the type is asserted below
            refused = error
        assert victim.read_text() == "before", "the jail's output went through the link"
        assert type(refused).__name__ == "PolicyStdioInWritableRoot", refused
        assert getattr(refused, "path", None) == f"{root}/out.txt"


def test_a_policy_that_does_not_reach_the_supervisors_interpreter_is_refused() -> None:
    """TASK-0029: the supervisor runs under the embedder's own interpreter, so the policy must
    mount it and every link on the way to it. A policy of the system tree alone, without the
    interpreter's own (wherever it lives), is refused naming the first path it misses."""
    system = tuple(p for p in ("/usr", "/bin", "/lib", "/lib64", "/etc") if Path(p).exists())
    if any(sys.executable.startswith(p + "/") for p in system):
        pytest.skip(
            "this interpreter lives under the system tree, so no system-only policy misses it"
        )
    with pytest.raises(brig.PolicyInterpreterUnreachable) as refused:
        create_bwrap_jail((sys.executable, "-c", "pass"), policy=FsPolicy(readable=system))
    assert refused.value.path == sys.executable
