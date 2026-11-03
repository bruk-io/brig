"""What is at a path on the host: the one fact a jail's compile needs about a write deny or a
mask (decision-0007). Plain data out (rule: infra names no brig type)."""

import os
import stat


def kinds(paths: tuple[str, ...]) -> dict[str, str]:
    """Each of `paths` as `"file"`, `"directory"` or `"absent"`, following links: a link is
    what it leads to, and a dangling one is absent."""
    found: dict[str, str] = {}
    for path in paths:
        try:
            mode = os.stat(path).st_mode
        except FileNotFoundError, NotADirectoryError:
            found[path] = "absent"
        else:
            found[path] = "directory" if stat.S_ISDIR(mode) else "file"
    return found
