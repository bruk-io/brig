"""The per-jail channel directory's lifecycle on the real filesystem (TASK-0001.26):
create it, private to the owning user, and remove it once a jail is done with it.

Imports nothing from `brig` (`brig-layers`'s own `infra` allow-list is empty) and takes
and returns plain data -- a host path, as a string, the same shape
`presentation/ports.py`'s `ChannelDirectoryPort` already uses for `allocate`.
"""

import shutil
import stat
from pathlib import Path


def create(path: str) -> None:
    """Make `path` exist, private to the owning user (mode 0o700), and every missing
    parent of it.

    Idempotent: a no-op on a path that already exists, except that its own mode is
    always reset to 0o700 -- a repeated call stays "private to the owning user" even
    should something else have widened it in between.
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(stat.S_IRWXU)


def remove(path: str) -> None:
    """Remove `path` and everything written inside it.

    `shutil.rmtree`'s own `FileNotFoundError` (or any other `OSError`) propagates:
    a caller that treats an already-gone directory as fine (every caller in this
    codebase so far) catches it itself, the same way it already does for the
    supervisor script's own `unlink`.
    """
    shutil.rmtree(path)
