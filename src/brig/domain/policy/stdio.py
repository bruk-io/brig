"""Where a jailed command's standard streams go (TASK-0028): plain data an embedder states."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stdio:
    """Each stream a host path, or `None` for the embedder's own. `stdin` is opened for reading;
    `stdout` and `stderr` for appending, created owner-only (0600) when absent. `"/dev/null"`
    discards a stream. Wherever a stream goes, the command gets a pipe, and the host pumps it to
    or from the file or the embedder's own fd (TASK-0042): handed a host inode, a jail could
    reopen it through `/proc/self/fd` with any mode the file allows its uid. So the command never
    gets a terminal, even with `INHERIT` on one: `isatty` is false in the jail. The pumps end with
    the jail. Nothing else of the embedder's reaches the command: these three numbers are the
    whole fd allow-list past the supervisor's own wire."""

    stdin: str | None = None
    stdout: str | None = None
    stderr: str | None = None


INHERIT = Stdio()
"""The default: the command's streams are pumped to and from the embedder's own fd 0, 1 and 2.
Bytes on the embedder's stdin that the pump read but the command never did are not given back."""
