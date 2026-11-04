"""TASK-0052: `link_chain` follows a lookup as the kernel does. The repro is
`test_files_link_chain_dotdot.py`; these are the cases written after it.

A gateway test of one `brig.infra` module (decision-0001 rule 4), on trees this test makes in a
throwaway directory; the kernel's own answer is `os.path.realpath` and `os.stat`.
"""

import os
from pathlib import Path

from brig.infra import files


def test_a_venv_interpreter_chain_names_each_link_replaced_in_turn(tmp_path: Path) -> None:
    """`python3 -> python`, `python -> <u>/py-3.15/bin/python3.15` (absolute), and `py-3.15 ->
    py-3.15.0b4` (a directory link): one path per link, then where it leads."""
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    install = tmp_path / "u" / "py-3.15.0b4" / "bin"
    install.mkdir(parents=True)
    (install / "python3.15").write_text("")
    (tmp_path / "u" / "py-3.15").symlink_to("py-3.15.0b4")
    (venv_bin / "python").symlink_to(f"{tmp_path}/u/py-3.15/bin/python3.15")
    (venv_bin / "python3").symlink_to("python")

    chain = files.link_chain(f"{venv_bin}/python3")

    assert chain == (
        f"{venv_bin}/python3",
        f"{venv_bin}/python",
        f"{tmp_path}/u/py-3.15/bin/python3.15",
        f"{tmp_path}/u/py-3.15.0b4/bin/python3.15",
    )


def test_dotdot_inside_a_links_target_is_taken_after_the_links_on_the_way(tmp_path: Path) -> None:
    """`a/l1 -> ../x/l2/../c`, `x/l2 -> y/z`: the target's `..` is taken from `x/y`, so the
    lookup reaches `x/y/c`, not `x/c`."""
    for directory in ("a", "x/y/z", "x/y/c"):
        (tmp_path / directory).mkdir(parents=True)
    (tmp_path / "x" / "c").mkdir()
    (tmp_path / "x" / "l2").symlink_to("y/z")
    (tmp_path / "a" / "l1").symlink_to("../x/l2/../c")
    path = f"{tmp_path}/a/l1"

    chain = files.link_chain(path)

    assert chain[-1] == os.path.realpath(path) == f"{tmp_path}/x/y/c"
    assert chain[1] == f"{tmp_path}/x/l2/../c"


def test_dotdot_before_any_link_is_taken_as_written(tmp_path: Path) -> None:
    """With no link before it, `..` removes the directory before it: the path is spelled
    without it."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").write_text("")

    assert files.link_chain(f"{tmp_path}/a/../b") == (f"{tmp_path}/b",)


def test_a_link_to_the_root_and_a_trailing_slash(tmp_path: Path) -> None:
    """A link to `/` is followed to `/`; empty components and `.` change nothing."""
    (tmp_path / "top").symlink_to("/")

    assert files.link_chain(f"{tmp_path}/./top/") == (f"{tmp_path}/top", "/")


def test_a_link_loop_stops_after_the_kernels_limit(tmp_path: Path) -> None:
    """Two links naming each other: the chain stops, as the kernel does with `ELOOP`."""
    (tmp_path / "p").symlink_to("q")
    (tmp_path / "q").symlink_to("p")

    assert files.link_chain(f"{tmp_path}/p") == (f"{tmp_path}/p", f"{tmp_path}/q")


def test_a_relative_path_is_returned_alone() -> None:
    """A lookup of a relative path depends on the working directory: nothing is read."""
    assert files.link_chain("logs/out") == ("logs/out",)


def test_every_chain_ends_where_the_kernel_leads(tmp_path: Path) -> None:
    """A mix of relative and absolute links, `..` after links and before them: the last path is
    the file the kernel opens."""
    (tmp_path / "d" / "e").mkdir(parents=True)
    (tmp_path / "d" / "e" / "f").write_text("here")
    (tmp_path / "up").symlink_to(f"{tmp_path}/d/e")
    (tmp_path / "d" / "side").symlink_to("../up/..")
    path = f"{tmp_path}/d/side/e/../e/f"

    chain = files.link_chain(path)

    assert chain[-1] == os.path.realpath(path)
    assert os.stat(chain[-1]).st_ino == os.stat(path).st_ino
