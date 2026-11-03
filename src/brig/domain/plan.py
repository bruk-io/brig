"""What a jail type's compile produces (decision-0001 rule 9)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    """The command a jail's supervisor runs as its child (decision-0002), and its candidate
    environment: not yet scrubbed, since `operations.create` applies the `EnvPolicy`. Empty by
    default, so the command then runs with no environment, `PATH` included."""

    argv: tuple[str, ...]
    env: frozendict[str, str] = frozendict()
