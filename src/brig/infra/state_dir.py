"""Brig's own runtime-state directory: where brig keeps artifacts it writes for
itself -- currently just the assembled supervisor script (`presentation/api.py`'s
`_supervisor_path`) -- instead of the caller-controlled, shared `/tmp`
(TASK-0006).

Functional core (`resolve`, pure) / imperative shell (`ensure`, the one I/O call)
split, the same discipline `infra/processes.py`'s own module docstring states for
itself: `resolve` only ever reads a mapping it is handed and builds a `Path`, never
touching the filesystem; `ensure` is the one function here that does.

This is brig's own operational configuration, not something a jailed command sees
or that `EnvPolicy` scrubs: `EnvPolicy` governs what a caller's `env` hands the
*jailed command* (`domain/policy/env.py`'s own docstring), never brig's own
host-side settings, and `BRIG_HOME` is exactly the latter -- conflating the two
would mean a caller's own `EnvPolicy` could silently redirect where brig writes its
own supervisor script.
"""

import os
from collections.abc import Mapping
from pathlib import Path

_BRIG_HOME = "BRIG_HOME"


def resolve(env: Mapping[str, str] = os.environ) -> Path:
    """Where brig's own state directory is, according to `env`: `BRIG_HOME`,
    taken exactly as given with no further default-resolution logic, when it is
    set and absolute; `~/.brig` otherwise.

    A relative `BRIG_HOME` is refused outright rather than silently accepted:
    it would depend on whatever the calling process's own working directory
    happens to be, and `compile_supervisor_launch` (`domain/jail_types/bwrap.py`)
    binds this directory into bwrap's own argv as a literal path string -- a
    relative one reproduces this task's original bug one layer further out,
    measured directly against real bwrap: `BRIG_HOME=relstate` produces `bwrap:
    Can't mkdir relstate: Read-only file system`, then `JailExitUnknown`, the
    identical signature this function exists to rule out. A caller wanting
    `~` expansion or a path relative to somewhere specific does that itself,
    before setting `BRIG_HOME` -- this function states the requirement, not a
    convenience resolver.

    Pure: reads only the mapping it is handed (`env`, `os.environ` by default --
    read, never mutated, and never touched here outside this one default
    argument), touches no filesystem, and raises only on the one input it
    refuses.

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
    """Make `path` exist (and every missing parent of it), then hand it straight
    back -- the one I/O call this module makes, kept apart from `resolve`'s pure
    computation of what `path` should be.

    A no-op, `exist_ok=True`, when `path` is already there -- repeated calls (one
    per process that starts a jail) are never an error.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
