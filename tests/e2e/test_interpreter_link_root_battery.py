"""TASK-0052 AC#5, against real bwrap: a policy whose readable root is the venv's interpreter link
itself passes `interpreter_refusal`, and the supervisor starts under it. bwrap binds what the
link leads to at the link's own path, so the jail never follows the links after it.

The interpreter's prefix is outside the chain the refusal checks: a venv's interpreter reads
`pyvenv.cfg` beside its `bin` and its standard library under the `home` that file names, so the
policy names both too, `home`'s directory as written there (itself reached through a link on a
uv install, and bound the same way).
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

from brig import FsPolicy, create_bwrap_jail, destroy_jail, run_jail

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)

_SYSTEM = ("/usr", "/bin", "/lib", "/lib64", "/etc")


def _venv_home(config: Path) -> str:
    """The `home` a venv's `pyvenv.cfg` names: the directory of the interpreter it was made
    from."""
    for line in config.read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "home":
            return value.strip()
    pytest.skip(f"{config} names no home")


def test_a_root_that_is_the_venv_interpreter_link_itself_starts_the_supervisor() -> None:
    """Readable: the system tree, the venv's interpreter link (not `.venv`), its `pyvenv.cfg`
    and the base install's directory. The jail runs `true` and exits 0."""
    if not os.path.islink(sys.executable):
        pytest.skip("this interpreter is not reached through a link, so there is none to bind")
    config = Path(sys.executable).parent.parent / "pyvenv.cfg"
    if not config.exists():
        pytest.skip("this interpreter is not a venv's")
    system = tuple(path for path in _SYSTEM if Path(path).exists())
    if any(sys.executable.startswith(path + "/") for path in system):
        pytest.skip("this interpreter lives under the system tree, which the policy mounts whole")
    base = os.path.dirname(_venv_home(config))
    policy = FsPolicy(readable=(*system, sys.executable, str(config), base))

    jail = create_bwrap_jail(("/bin/true",), policy=policy)
    try:
        assert run_jail(jail, timeout_s=15) == 0
    finally:
        destroy_jail(jail)
