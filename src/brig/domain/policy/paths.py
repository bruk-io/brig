"""Which paths a jail may see (decision-0001's layout; TASK-0001.16): plain data,
nothing else (rule 2) -- `domain/jail_types/bwrap.py`'s `compile_supervisor_launch`
is what translates an `FsPolicy` into bwrap's own `--ro-bind`/`--bind` flags; this
module states the policy, never the mechanism that enforces it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Bind:
    """One path this policy makes visible inside a jail.

    `host_path` is bound at `jail_path` inside the jail's own root -- the two may
    differ (a jail can see a host path under a different name than it has on the
    host), though every caller in this codebase so far binds a path at the same
    name it already has. Read-only unless `writable` is set, the safer default:
    an embedder names a path writable only when it means to let the jailed command
    change it.
    """

    host_path: str
    jail_path: str
    writable: bool = False


@dataclass(frozen=True)
class FsPolicy:
    """The complete set of paths visible inside a jail: exactly what `binds` names,
    in the order given, nothing implied beyond it. A jail type's compile (`rule 3`)
    is the one thing that reads this to build its own jail's filesystem; nothing
    about *which* paths an embedder should ask for is decided here -- a real
    per-embedder policy is that embedder's own choice, not this module's.
    """

    binds: tuple[Bind, ...]


WHOLE_HOST_READ_ONLY = FsPolicy(binds=(Bind(host_path="/", jail_path="/", writable=False),))
"""The default policy every bwrap jail gets until an embedder states its own
(decision-0001's order, step 4; `domain/jail_types/bwrap.py`'s own
`compile_supervisor_launch`): the whole host root, bound read-only -- the thinnest
thing that lets the supervisor's own file be reachable inside the jail at all.
Reproduces exactly the flags the placeholder `--ro-bind / /` bind produced before
this module existed (`tests/unit/test_bwrap_compile.py`'s own byte-exact assertion
on `compile_supervisor_launch`'s output is the proof nothing currently passing
regressed when this became the default rather than the only option).
"""
