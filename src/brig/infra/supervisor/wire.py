"""The supervisor's wire protocol: newline-delimited JSON message shapes.

decision-0002's minimal first version of the supervisor: one `exec` request in
(the real command to run, and the environment to run it in), and a stream of
`started`/`exited`/`done` events out, one per line, reporting what happened to
the one command the supervisor was asked to run. This module names the shapes
both ends agree on; it performs no I/O itself (reading and writing the actual
lines is each end's own job -- `program.py`'s, inside the jail, and
`infra/supervisor/link.py`'s, on the host, a later step of TASK-0001.15).

Stdlib only, no import of anything else under `brig` (decision-0001 rule 17):
once `program.py` is assembled alongside this module into the one file dropped
as PID 1 inside the jail's own namespace, nothing installed outside that one
file can be reachable from inside it. `program.py` itself does *not* import
this module -- see its own docstring for why -- so this module's only
in-process reader is `link.py`, the host's end of the same protocol
(TASK-0001.15 step 3; DRAFT-0009 AC#3, settled there: `link.py` never crosses
into the jail, so importing this module costs it nothing). `Event`,
`encode_exec_request` and `decode_event` dropped their leading underscore for
exactly that -- `link.py` calls them in real code now, not only in a docstring
(decision-0001 rule 6's `over-exposed-module-symbol`/`under-exposed-access`),
the same convention `domain/effects.py` dropped for `StartSupervisedCommand`/
`AwaitSupervisorDone` once `operations.py` called those in (TASK-0001.15 step 4).
`WireError` drops its own underscore in that same step: `link.py`'s
`_await_one_done` now does name it in an `except` clause, catching a malformed
line the same way it catches a read-side `OSError` -- both fold into
`SupervisorDoneUnknown` rather than escaping, since neither leaves anything left
to trust from this supervisor. `MessageKind` stays private still: nothing outside
this module matches on one of its members by name -- `done_exit_code` (added the
same step, for exactly the "which event is this" question `link.py` needs to
answer without that access) keeps the match inside this module, where the enum is
not private to the caller. Every other name here (the three event encoders, the
exec-request decoder) still has no caller outside this module either --
`program.py` duplicates rather than calls them -- so those stay private too.

Rule 8: a closed `TypedDict` for every JSON shape crossing a boundary, a
`StrEnum` for every value sent. `TypedDict` is not literally one of rule 7's
four named class forms (frozen dataclass, `Protocol`, `Enum`/`StrEnum`,
`Exception` subclass) -- it is, like `Protocol`, a `typing` construct that
states a shape rather than claiming a real is-a relationship, so
`pypeeker_rules/brig.py`'s `brig-class-forms` exemption list is extended here
to include it, alongside `Protocol`/`Enum`/`StrEnum`.

DRAFT-0010's resolution: `REQUEST_FD`/`EVENTS_FD` name the two fixed file
descriptor numbers the wire protocol actually travels on inside the supervised
process -- `program.py` reads the one exec request from `REQUEST_FD` and writes
every `started`/`exited`/`done` event to `EVENTS_FD`, never through fd 0/1/2
any more. Before this, the protocol ran over the supervisor's own stdin/stdout
(fd 0/1), which left the supervised command it then started with nowhere of
its own to put its stdio: it inherited the supervisor's fd 0/1 outright (the
control-channel authentication hole TASK-0001.15's adversarial review found and
plugged with a sealed pipe -- a stopgap, not an answer) or, after that plug, a
dead end that silently rewrote its exit code (the sealed pipe's own
fix-confirmation update). Moving the wire itself off 0/1/2 removes the
conflict instead of mediating it: those three numbers are free again for the
supervised command to inherit from whatever the jail type's own driver set up
for the supervisor to inherit in turn (`infra/supervisor/link.py`'s `_start`,
TASK-0001.16's `inheritable_fds`) -- exactly where they would have come from
had no supervisor sat in between at all.

`3`/`4` are the first two numbers past the three standard streams, the same
reasoning this project already uses for `_INHERITABLE_FDS = (0, 1, 2)`
(`domain/jail_types/bwrap.py`): a small, fixed, documented convention both
ends of one spawn agree on ahead of time, not a number either side discovers
at runtime -- there is exactly one supervisor per jail and exactly one wire
protocol, so a fixed pair costs nothing an embedder needs to observe or pass
exactly one `--fd` flag of their own around. Measured, not assumed: an
inherited, explicitly-marked-inheritable fd 4 does survive `bwrap`'s own exec
into a real jail's namespace under `--unshare-all`/`--as-pid-1` (a real
`--privileged ubuntu:24.04` container, a parent writing through it and reading
the bytes back) -- fd passing is independent of every namespace `bwrap`
isolates, which only partition what a process may *name* (paths, pids,
mounts), never which already-open fds it keeps.

`program.py` duplicates these two numbers as its own private constants, the
same way it duplicates the message shapes above -- see its own module
docstring for why it cannot import this module at all once assembled, which is
also why nothing enforces the two staying in agreement except this comment and
whatever test pins it.
"""

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import TypedDict, assert_never, cast

REQUEST_FD = 3
"""The fd `program.py` reads the one `exec` request from, inside the supervised
process. `infra/supervisor/link.py`'s `_start` dup2s the request pipe's read end
onto this number in the new process, by name, rather than onto fd 0 -- freeing
fd 0 for the supervised command it then starts to inherit instead (this
module's own docstring).
"""

EVENTS_FD = 4
"""The fd `program.py` writes every `started`/`exited`/`done` event to, inside
the supervised process. `infra/supervisor/link.py`'s `_start` dup2s the events
pipe's write end onto this number, by name, rather than onto fd 1 -- freeing fd
1 for the supervised command it then starts to inherit instead (this module's
own docstring).
"""


class _MessageKind(StrEnum):
    """Every shape this module defines, named once, matching its own `kind` field."""

    EXEC = "exec"
    STARTED = "started"
    EXITED = "exited"
    DONE = "done"


class _ExecRequest(TypedDict, closed=True):
    """The one incoming message: the real command to run as the supervisor's
    own child, and the environment to run it in.
    """

    kind: _MessageKind
    argv: list[str]
    env: dict[str, str]


class _StartedEvent(TypedDict, closed=True):
    """Reported once the supervisor has started its one child."""

    kind: _MessageKind
    pid: int


class _ExitedEvent(TypedDict, closed=True):
    """Reported once the supervisor's one started child -- not an orphan
    reparented to it afterward -- has exited.
    """

    kind: _MessageKind
    pid: int
    exit_code: int


class _DoneEvent(TypedDict, closed=True):
    """Reported once nothing remains for the supervisor to reap: its own
    started child and every orphan reparented to it as PID 1 are all gone.

    `exit_code` is the started child's own exit code (`_ExitedEvent.exit_code`
    for the same run), carried again here so a reader that only watches for
    `done` -- the shape `domain/effects.py`'s `_AwaitSupervisorDone` names --
    never has to also keep the earlier `exited` event around to learn it.
    """

    kind: _MessageKind
    exit_code: int


type Event = _StartedEvent | _ExitedEvent | _DoneEvent
"""The closed set of outgoing messages `decode_event` may return, matched to
`assert_never` the same way `domain/effects.py`'s `Effect` union is (rule 9).
"""


class WireError(Exception):
    """Raised when a line read from the wire is not one of this module's
    message shapes.

    Args:
        line: The raw line that could not be decoded.
    """

    def __init__(self, line: str) -> None:
        super().__init__(f"malformed wire message: {line!r}")
        self.line = line


def encode_exec_request(argv: tuple[str, ...], env: Mapping[str, str]) -> str:
    """Encode an `exec` request as one newline-delimited JSON line."""
    message: _ExecRequest = {"kind": _MessageKind.EXEC, "argv": list(argv), "env": dict(env)}
    return json.dumps(message) + "\n"


def _decode_exec_request(line: str) -> _ExecRequest:
    """Decode one line as an `_ExecRequest`.

    Raises:
        WireError: `line` is not a well-formed `exec` request.
    """
    try:
        raw = json.loads(line)
        if raw["kind"] != _MessageKind.EXEC.value:
            raise WireError(line)
        return {
            "kind": _MessageKind.EXEC,
            "argv": [str(arg) for arg in raw["argv"]],
            "env": {str(name): str(value) for name, value in raw["env"].items()},
        }
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise WireError(line) from exc


def _encode_started(pid: int) -> str:
    """Encode a `started` event as one newline-delimited JSON line."""
    message: _StartedEvent = {"kind": _MessageKind.STARTED, "pid": pid}
    return json.dumps(message) + "\n"


def _encode_exited(pid: int, exit_code: int) -> str:
    """Encode an `exited` event as one newline-delimited JSON line."""
    message: _ExitedEvent = {"kind": _MessageKind.EXITED, "pid": pid, "exit_code": exit_code}
    return json.dumps(message) + "\n"


def _encode_done(exit_code: int) -> str:
    """Encode a `done` event as one newline-delimited JSON line."""
    message: _DoneEvent = {"kind": _MessageKind.DONE, "exit_code": exit_code}
    return json.dumps(message) + "\n"


def decode_event(line: str) -> Event:
    """Decode one line as whichever `Event` shape its `kind` names.

    Raises:
        WireError: `line` is not well-formed JSON, names no `kind` this
            module recognizes as an event (an `exec` request's `kind`
            included -- that shape only ever travels the other way), is
            missing a field its `kind` requires, or names a field whose
            value cannot be coerced to the type its shape requires (`pid`,
            `exit_code`: both `int(...)`, which raises `ValueError` on a
            non-numeric value such as `{"kind": "started", "pid": "abc"}`
            -- measured escaping this function as a raw `ValueError` before
            `ValueError` joined this `except` clause, past every caller
            that only ever named `WireError`).
    """
    try:
        raw = json.loads(line)
        kind = _MessageKind(raw["kind"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        raise WireError(line) from exc
    try:
        match kind:
            case _MessageKind.STARTED:
                return {"kind": kind, "pid": int(raw["pid"])}
            case _MessageKind.EXITED:
                return {"kind": kind, "pid": int(raw["pid"]), "exit_code": int(raw["exit_code"])}
            case _MessageKind.DONE:
                return {"kind": kind, "exit_code": int(raw["exit_code"])}
            case _MessageKind.EXEC:
                raise WireError(line)
            case _ as unreachable:
                assert_never(unreachable)
    except (KeyError, TypeError, ValueError) as exc:
        raise WireError(line) from exc


def done_exit_code(event: Event) -> int | None:
    """Return a `done` event's exit code, or `None` if `event` is a `started` or
    `exited` event instead.

    The one place code outside this module asks which of `Event`'s three shapes
    arrived without matching on `_MessageKind` itself (decision-0001 rule 6's
    `under-exposed-access`: that enum stays private, this module's own docstring):
    `link.py`'s `_await_one_done` calls this once per event read, to tell "not done
    yet, keep waiting" apart from "done, here is the exit code" without needing to
    name the kind each shape carries.
    """
    if event["kind"] != _MessageKind.DONE:
        return None
    return cast(_DoneEvent, event)["exit_code"]
