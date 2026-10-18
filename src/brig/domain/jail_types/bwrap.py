"""bwrap's slice of the domain (decision-0001 rule 3): compiling a request, nothing else.

The matching driver, ``presentation/drivers/bwrap.py``, performs the effects
``domain/operations.py`` yields for whatever ``Plan`` this module compiles; no module here
imports that driver, or any other jail type's modules (rule 3).
"""

from brig.domain.plan import Plan

_BWRAP_ARGV: tuple[str, ...] = (
    "bwrap",
    "--ro-bind",
    "/",
    "/",
    "--unshare-all",
    "--die-with-parent",
    "--new-session",
    "--",
)
"""bwrap's own flags, ahead of the command it runs as the jail's one process.

``--ro-bind / /`` gives the jail a root with something in it: without any bind, bwrap
pivots into an empty new root and ``execvp`` of the command finds nothing there to run,
regardless of exit code. A real filesystem policy -- which paths, read-only or not --
is a later slice's addition (decision-0001's order, step 4); the walking skeleton only
needs `true` to be reachable, so the whole host root, read-only, is the thinnest thing
that satisfies that without yet deciding the policy. ``--unshare-all`` isolates every
namespace bwrap can; ``--die-with-parent`` ties the jail's lifetime to the process that
started it.

``--new-session`` (TASK-0001.05 AC#2) closes the TIOCSTI escape bwrap's own
documentation warns about: a process sharing a controlling terminal with something
outside the jail can, without its session detached from that terminal, inject
keystrokes back onto it via the TIOCSTI ioctl and escape through whatever reads them
next. Stated here, as this jail type's own policy, rather than left to infra's spawn:
on the toolchain this project's own CI runs, this flag is the *only* thing closing that
hole, and it is load-bearing rather than defense in depth.

That is a correction of what TASK-0001.05's review measured on one host. The review
found infra's ``os.posix_spawnp(..., setsid=True)`` (TASK-0001.06's safe-spawn work)
running unconditionally, before bwrap's own argv is ever parsed, and concluded this
flag could never be credited for the closure. Measured since, on real Linux
(TASK-0001.12): ``setsid=True`` is not available on every interpreter -- it is compiled
out of uv's managed CPython, the build this project's ``pyproject.toml`` and CI select
-- so ``brig.infra.processes.spawn`` falls back to a new process group alone there,
which leaves the controlling terminal shared and the hole open. Infra reports which it
got as ``SpawnedProcess.session_detached``. Where that is ``False``, nothing but
``--new-session`` closes this, and the flag's contribution is attributable after all;
where it is ``True``, infra's session already closed it first and the flag is the
redundant half, keeping the property true should that ever stop. Either way
``tests/e2e/test_tiocsti_battery.py`` grades the property end to end (TIOCSTI stays
denied) rather than which layer denies it; grading the attribution itself is still
tracked separately (TASK-0001.11).
"""

_INHERITABLE_FDS: tuple[int, ...] = (0, 1, 2)
"""The complete set of file descriptors bwrap's jailed process may inherit across the
spawn (`Plan.inheritable_fds`'s own docstring: a complete allow-list, not an addition
to an implicit default).

Just stdin, stdout and stderr: bwrap's own argv above opens no fd of its own that needs
naming (no ``--info-fd``, no ``--sync-fd``; this jail type uses neither), and the jailed
command is an ordinary one that reads and writes its own standard streams the way any
unconfined command would -- closing those would add no boundary the mount and namespace
policy does not already state, just a jail whose command cannot do ordinary I/O. It
would also make AC#3's own battery unbuildable: a positive control that plants a
violation and checks it is blocked needs the jailed command to report what it saw,
which means stdout has to survive. Nothing else is named because nothing else is used
yet: an embedder fd for IPC, or a channel of brig's own (decision-0001's order, step
4), is a later jail-type choice to make, not one this slice has a caller for.
"""


def compile_run(command: tuple[str, ...]) -> Plan:
    """Compile a request to run `command` as a bwrap jail's one process.

    This jail type never refuses a request (see `domain/plan.py`), so the walking
    skeleton's compile always produces a `Plan`.
    """
    return Plan(argv=(*_BWRAP_ARGV, *command), inheritable_fds=_INHERITABLE_FDS)
