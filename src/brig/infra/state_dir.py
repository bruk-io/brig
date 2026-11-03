"""brig's state directory, where it keeps what it writes for itself (supervisor scripts,
channel directories, placeholder records) instead of the shared `/tmp` (TASK-0006).
`BRIG_HOME` is brig's own setting, never something `EnvPolicy` scrubs.
"""

import os
from collections.abc import Mapping
from pathlib import Path

_BRIG_HOME = "BRIG_HOME"


def resolve(env: Mapping[str, str] = os.environ) -> Path:
    """brig's state directory per `env`: `BRIG_HOME` when set, else `~/.brig`. Pure.

    A relative `BRIG_HOME` is refused: it lands in bwrap's argv as given, and bwrap fails with
    `Can't mkdir relstate: Read-only file system` (measured).

    Raises:
        ValueError: `BRIG_HOME` is set to a value that is not an absolute path.
    """
    value = env.get(_BRIG_HOME)
    if not value:
        return Path.home() / ".brig"
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(value)
    return path


def ensure(path: Path) -> Path:
    """Make `path` and its missing parents if absent, and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_empty(state_dir: Path) -> Path:
    """Make `<state_dir>/empty` exist as an empty directory nobody can write (mode 0555) and
    hand it back: the source a jail mounts, read-only, over a masked directory or an absent
    path (decision-0007).

    Raises:
        OSError: it could not be made, or something is already in it.
    """
    empty = state_dir / "empty"
    empty.mkdir(mode=0o555, exist_ok=True)
    os.chmod(empty, 0o555)
    if any(empty.iterdir()):
        raise OSError(f"{empty} is not empty")
    return empty
