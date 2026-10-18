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
    """What a jail type compiled a request into: the argv its one process runs.

    ``inheritable_fds`` is the jail type's own policy (decision-0001 rule 11; TASK-0001.05
    AC#1) for which file descriptors its one process may keep open across the spawn: the
    complete allow-list, not an addition to some implicit default stdio exemption -- the
    spawn path closes every fd it finds open and inheritable that is not named here,
    stdin/stdout/stderr included, unless the jail type names them itself. Naming the
    complete set here, rather than having the spawn path special-case the standard
    streams on every jail type's behalf, keeps the policy where rule 11 puts it: in the
    jail type's own compile, which is the only place that knows what its command
    legitimately needs (bwrap's ``compile_run`` documents its own choice). No
    default: a compile that states no fds states, as a value nobody chose, the most
    aggressive policy there is -- closing even its own standard streams -- so every
    jail type's compile names its own choice explicitly, or mypy strict refuses it.
    """

    argv: tuple[str, ...]
    inheritable_fds: tuple[int, ...]
