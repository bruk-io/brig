"""What a jail type's compile produces: a plan, never a decision deferred.

decision-0001 rule 9: a deciding function returns an Enum member or a union of frozen
dataclasses, matched to ``assert_never``; compile returns ``Plan | Refused``. The walking
skeleton's one jail type (bwrap, running ``true``) never refuses a request, so nothing in
this slice constructs a ``Refused`` -- adding that type now, with no caller and no test
that ever produces one, would be an unused name this slice cannot justify. The jail type
that first needs to refuse a request adds it here, alongside the match that handles it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    """What a jail type compiled a request into: the real command its jail's
    supervisor runs as its own child (decision-0002), and the environment to run it
    in.

    TASK-0001.15 step 4: before the supervisor, ``argv`` was the jail type's own
    fully-wrapped launch line (bwrap's flags plus the command, `Spawn`'s own argv)
    and this was the one process `create()` spawned directly. Now the jail's one
    process *is* the supervisor, started by presentation's driver through
    whatever argv that jail type's own `compile_supervisor_launch`-shaped function
    builds (never carried here: domain does no I/O, so it cannot locate the
    supervisor's own file -- `domain/jail_types/bwrap.py`'s own docstring) -- and
    ``argv``/``env`` here are instead what `operations.create()` hands that
    supervisor to run as *its* child, over the wire.

    ``env`` defaults to empty, and is itself a candidate, not yet scrubbed:
    ``operations.create()`` is TASK-0001.17's one caller of ``scrub_env``
    (``domain/policy/env.py``), and filters this field down to whatever its own
    ``EnvPolicy`` names before the supervised command ever sees it. A jail type's
    compile (`compile_run`) still has no reason to read that policy itself (rule 2;
    rule 3 -- a jail type is a slice, with no call into another module's policy),
    so this field is still no jail type's own scrubbed result, only what it has to
    offer `create()` to scrub. Left unset, every supervised command still runs with
    no environment at all (a known gap stated honestly rather than hidden -- an
    embedder's own command should name an absolute path until some caller
    populates this field, since ``PATH`` itself is one of the things an empty
    environment loses).

    ``inheritable_fds`` is the jail type's own fd-allow-list policy (decision-0001
    rule 11; TASK-0001.05 AC#1), carried here unchanged in shape -- but with no
    current reader: `operations.create()` yields `StartSupervisedCommand`, which
    carries no `inheritable_fds` field (`domain/effects.py`'s own "Unresolved
    here" note), so this plan's fd policy no longer reaches any effect on the
    normal path. Left in place, not removed, as that same open question's
    record -- whichever of the supervisor's own exec or a later effect field
    ends up enforcing it is still TASK-0001.15's later step to decide, not this
    one.
    """

    argv: tuple[str, ...]
    inheritable_fds: tuple[int, ...]
    env: tuple[tuple[str, str], ...] = ()
