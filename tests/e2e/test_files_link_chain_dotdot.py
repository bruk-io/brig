"""TASK-0052's repro: `link_chain` must resolve a link before the `..` after it, as the kernel does.

A lookup of `a/link/../b` follows `a/link` first and then takes `..` from where the link leads, so
with `a/link` pointing at `x/y` it reaches `x/b`. Normalising `..` as text first drops the link
and the lookup is followed to `a/b` instead, a different file.

A gateway test of one `brig.infra` module (decision-0001 rule 4), on a tree this test makes in a
throwaway directory; the kernel's own answer is `os.stat` and `os.path.realpath`.
"""

import os
from pathlib import Path

from brig.infra import files


def test_dotdot_after_a_link_is_taken_from_where_the_link_leads(tmp_path: Path) -> None:
    """`a/link -> ../x/y`, and both `a/b` and `x/b` exist: the chain ends at `x/b`, the file the
    kernel opens for `a/link/../b`."""
    (tmp_path / "a").mkdir()
    (tmp_path / "x" / "y").mkdir(parents=True)
    (tmp_path / "a" / "b").write_text("the text's answer")
    (tmp_path / "x" / "b").write_text("the kernel's answer")
    (tmp_path / "a" / "link").symlink_to("../x/y")
    path = f"{tmp_path}/a/link/../b"

    chain = files.link_chain(path)

    assert os.stat(chain[-1]).st_ino == os.stat(path).st_ino
    assert chain[-1] == os.path.realpath(path)
