"""What is at a policy path on the host, and where it leads: the facts a jail's compile and its
refusal need (decision-0007). Plain data out (rule: infra names no brig type)."""

import os
import stat


def facts(paths: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    """Each of `paths` as `(kind, resolved)`: `kind` is `"file"`, `"directory"` or `"absent"`,
    following links (a link is what it leads to, a dangling one is absent), and `resolved` is where
    the path leads once every link on the way is followed (`os.path.realpath`), so a caller can
    tell a path reached through a link from one that is not. Any other `OSError` from the
    `stat` propagates, such as `PermissionError` for a directory on the way this process cannot
    search, or `ELOOP` for a symbolic link loop: the path's kind is then unknown, not absent."""
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


_MAX_LINKS = 40
"""How many links one lookup follows before the kernel gives up (`ELOOP`)."""


def link_chain(path: str) -> tuple[str, ...]:
    """Every path a lookup of `path` passes through: `path` itself, then, each time a component
    on the way is a symbolic link, the path with that link replaced by its target, until none
    is. Absolute and normalised; stops after `_MAX_LINKS` links, as the kernel does. An
    `OSError` from reading a link propagates: one this process may not read (another user's
    `/proc/<pid>/cwd`), or one replaced or removed between finding it and reading it."""
    chain = [os.path.normpath(path)]
    for _ in range(_MAX_LINKS):
        current = chain[-1]
        parts = current.split("/")
        for depth in range(2, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            if os.path.islink(prefix):
                target = os.readlink(prefix)
                base = os.path.dirname(prefix)
                rest = "/".join(parts[depth:])
                joined = os.path.join(base, target, rest) if rest else os.path.join(base, target)
                chain.append(os.path.normpath(joined))
                break
        else:
            return tuple(dict.fromkeys(chain))
    return tuple(dict.fromkeys(chain))


def link_count(path: str) -> int:
    """How many names `path`'s file has (`st_nlink`, not following a link at `path`); 1 when
    nothing is there."""
    try:
        return os.lstat(path).st_nlink
    except OSError:
        return 1


def first_link(path: str) -> str | None:
    """The first component on the way to `path` (itself included) that is a symbolic link, as a
    path, or `None` when none is."""
    parts = [part for part in path.split("/") if part]
    for depth in range(1, len(parts) + 1):
        prefix = "/" + "/".join(parts[:depth])
        if os.path.islink(prefix):
            return prefix
    return None


def own_regular_file(path: str) -> bool:
    """Whether `path` is absent (brig will create it, owned by this process) or a regular file
    this process's user owns, not following a link at `path`."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
