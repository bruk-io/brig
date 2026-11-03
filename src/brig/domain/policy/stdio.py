"""Where a jailed command's standard streams go (TASK-0028): plain data an embedder states."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stdio:
    """Each stream a host path, or `None` for the embedder's own. `stdin` is opened for reading;
    `stdout` and `stderr` for appending, created owner-only (0600) when absent. `"/dev/null"`
    discards a stream. Nothing else of the embedder's reaches the command: these three numbers
    are the whole fd allow-list past the supervisor's own wire."""

    stdin: str | None = None
    stdout: str | None = None
    stderr: str | None = None


INHERIT = Stdio()
"""The default: the command's streams are the embedder's own."""
