"""bwrap's slice of the domain (decision-0001 rule 3): compiling a request, nothing else.

The matching driver, ``presentation/drivers/bwrap.py``, performs the effects
``domain/operations.py`` yields for whatever ``Plan`` this module compiles; no module here
imports that driver, or any other jail type's modules (rule 3).

TASK-0001.15 step 4: ``compile_run`` no longer wraps the real command in bwrap's own
flags -- the jail's one process is the supervisor now (decision-0002), and ``Plan.argv``
is the command `operations.create()` hands it to run as *its* child, over the wire, not
something this jail type spawns directly any more. ``compile_supervisor_launch`` is the
new home for bwrap's own wrapping job: presentation's driver calls it with wherever it
found the supervisor's own file, since locating that file is I/O domain does not do
(rule 2).

TASK-0001.16: ``compile_supervisor_launch`` now also takes an ``FsPolicy``
(`domain/policy/paths.py`) and translates its binds into bwrap's own
``--ro-bind``/``--bind`` flags, ahead of the namespace-isolation flags below --
replacing the single hardcoded ``--ro-bind / /`` placeholder this module used to
carry as ``_BWRAP_ARGV``. That placeholder is gone; ``WHOLE_HOST_READ_ONLY``
(`domain/policy/paths.py`) is the default ``FsPolicy`` every caller gets when it
names none of its own, reproducing the exact flags the old placeholder produced
(`tests/unit/test_bwrap_compile.py`'s byte-exact assertion on
``compile_supervisor_launch``'s output is the proof nothing currently passing
regressed). This landed on ``compile_supervisor_launch``, not ``compile_run``:
by TASK-0001.15 step 4, ``compile_run`` builds no bwrap argv at all any more (it
only names the real command the supervisor runs as its own child, see `Plan`'s own
docstring) -- a policy parameter there would reach no flag, the exact "no current
reader" gap `Plan.inheritable_fds`'s own docstring already records for a different
field. ``compile_supervisor_launch`` is what actually builds the supervisor's own
bwrap-wrapped launch line, so that is where a filesystem policy has to land to mean
anything.
"""

from brig.domain.plan import Plan
from brig.domain.policy.paths import WHOLE_HOST_READ_ONLY, FsPolicy

_NAMESPACE_FLAGS: tuple[str, ...] = (
    "--unshare-all",
    "--die-with-parent",
    "--new-session",
    "--as-pid-1",
    "--",
)
"""bwrap's own namespace-isolation flags, after whatever `_compile_binds` names for
a policy's binds and ahead of whatever this jail type's driver names as the jail's
one process -- the supervisor (decision-0002), by way of `compile_supervisor_launch`.

A policy's binds have to come first: without at least one bind, bwrap pivots into an
empty new root and `execvp` finds nothing there to run, regardless of exit code --
`WHOLE_HOST_READ_ONLY`'s whole-host read-only bind is the thinnest policy that lets
the supervisor's own file be reachable inside the jail at all (presentation's own
wiring documents exactly how it relies on that). ``--unshare-all`` isolates every
namespace bwrap can; ``--die-with-parent`` ties the jail's lifetime to the process
that started it.

``--as-pid-1`` (TASK-0001.15 step 4, measured against real bwrap in a privileged
Docker container -- bwrap itself refuses ``--unshare-all`` outside one, a container
limitation, not a finding about this flag) is load-bearing for decision-0002's own
premise, not an optional hardening: ``--unshare-all`` implies ``--unshare-pid``, and
bwrap's *default* behaviour there installs its own reaper process as the namespace's
real PID 1, with whatever this argv names after ``--`` running as PID 2 instead --
measured directly (the supervisor's own ``started`` event named a pid of 3, not 1,
without this flag; 1, with it). Without it, an orphan reparented inside the
namespace reparents to bwrap's own reaper, never to the supervisor, and
``program.py``'s own "reaps everything reparented to it, including orphans"
(its own module docstring) silently stops being true for anything bwrap's reaper
catches instead. ``--as-pid-1`` makes the supervisor itself the one process bwrap
execs into that role, with no separate reaper in between.

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
"""The complete set of file descriptors bwrap's own jailed process may inherit across
the spawn (`Plan.inheritable_fds`'s own docstring: a complete allow-list, not an
addition to an implicit default).

Just stdin, stdout and stderr: bwrap's own argv above opens no fd of its own that needs
naming (no ``--info-fd``, no ``--sync-fd``; this jail type uses neither). Named here
unchanged since the walking skeleton, when this was the real command's own policy --
TASK-0001.15 step 4 made the jail's directly-spawned process the supervisor instead
(`Plan`'s own docstring), and `StartSupervisedCommand` carries no `inheritable_fds`
field to hand this to, so the value `compile_run` returns here currently reaches no
effect at all. Left stated rather than deleted, as the open question `domain/effects.py`
already records: whichever of the supervisor's own exec or a later effect field ends up
enforcing this is still open.
"""


def compile_run(command: tuple[str, ...], env: tuple[tuple[str, str], ...] = ()) -> Plan:
    """Compile a request to run `command`, in `env`, as the one command bwrap's
    supervisor runs as its own child (decision-0002).

    This jail type never refuses a request (see `domain/plan.py`), so the walking
    skeleton's compile always produces a `Plan`.
    """
    return Plan(argv=command, inheritable_fds=_INHERITABLE_FDS, env=env)


def _compile_binds(policy: FsPolicy) -> tuple[str, ...]:
    """Translate `policy`'s own binds into bwrap's `--ro-bind`/`--bind` flags: one
    bind, one `(flag, host_path, jail_path)` triple, in the order `policy.binds`
    names them -- `--bind` for a writable `Bind`, `--ro-bind` otherwise, each
    followed by its `host_path` then its `jail_path` (bwrap's own argument order
    for both flags).
    """
    return tuple(
        flag
        for bind in policy.binds
        for flag in ("--bind" if bind.writable else "--ro-bind", bind.host_path, bind.jail_path)
    )


def compile_supervisor_launch(
    supervisor_path: tuple[str, ...], policy: FsPolicy = WHOLE_HOST_READ_ONLY
) -> tuple[str, ...]:
    """Wrap `supervisor_path` in this jail type's own bwrap flags, so bwrap starts
    the supervisor named there as the jail's one process, seeing exactly the paths
    `policy` names and nothing else (TASK-0001.16) -- this function's own job
    before TASK-0001.15 step 4 pointed it at the real command directly, now aimed
    at the supervisor instead (decision-0002).

    `policy` defaults to `WHOLE_HOST_READ_ONLY` (`domain/policy/paths.py`): the
    whole host root, read-only -- the thinnest policy that lets the supervisor's
    own file be reachable inside the jail at all, reproducing exactly the flags
    the single hardcoded `--ro-bind / /` bind this function carried before this
    parameter existed, so a caller that never names a policy of its own sees no
    change.

    `supervisor_path` is presentation's own concern: this jail type's driver finds
    wherever the file `infra/supervisor/wire.py` and `program.py` assemble into
    actually lives (`domain/jail_types/bwrap.py`'s module docstring) and hands the
    already-resolved argv in here as plain strings -- domain states the policy
    (which paths, namespace isolation, `--new-session`'s TIOCSTI closure) but does
    no I/O of its own to locate anything (rule 2).
    """
    return ("bwrap", *_compile_binds(policy), *_NAMESPACE_FLAGS, *supervisor_path)
