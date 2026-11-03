"""What is at a policy path on the host, and where it leads: the facts a jail's compile and its
refusal need (decision-0007). Plain data out (rule: infra names no brig type)."""

import os
import stat


def facts(paths: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    """Each of `paths` as `(kind, resolved)`: `kind` is `"file"`, `"directory"` or `"absent"`,
    following links (a link is what it leads to, a dangling one is absent), and `resolved` is where
    the path leads once every link on the way is followed (`os.path.realpath`), so a caller can
    tell a path reached through a link from one that is not."""
    found: dict[str, tuple[str, str]] = {}
    for path in paths:
        try:
            mode = os.stat(path).st_mode
        except FileNotFoundError, NotADirectoryError:
            kind = "absent"
        else:
            kind = "directory" if stat.S_ISDIR(mode) else "file"
        found[path] = (kind, os.path.realpath(path))
    return found
