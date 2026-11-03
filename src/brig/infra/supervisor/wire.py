"""The supervisor's wire protocol (decision-0002): one `exec` request in, then `started`,
`exited` and `done` events out, each one newline-delimited JSON line. Shapes only, no I/O.

The protocol travels on fds 3 and 4, never 0, 1 or 2, so the supervised command inherits the
embedder's stdio unchanged. A fd survives bwrap's exec into the jail under `--unshare-all` and
`--as-pid-1` (measured). `program.py` cannot import this module once assembled, so it repeats
these numbers and shapes; the supervisor's e2e gateway tests run it against this module's.
"""

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import TypedDict, assert_never, cast

REQUEST_FD = 3
"""The supervisor's fd for the one `exec` request."""

EVENTS_FD = 4
"""The supervisor's fd for its events."""


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
    """Reported once nothing remains for the supervisor to reap: its child and every orphan
    reparented to it are gone. `exit_code` is the child's, repeated from `exited`."""

    kind: _MessageKind
    exit_code: int


type Event = _StartedEvent | _ExitedEvent | _DoneEvent
"""The closed set of events `decode_event` returns."""


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
    """Decode one line as the `Event` its `kind` names.

    Raises:
        WireError: `line` is not JSON, names no event `kind` (an `exec` included), lacks a field,
            or holds a field that is not an int; never a bare `ValueError`, which once escaped
            past callers that catch only `WireError` (TASK-0001.15).
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
    """A `done` event's exit code, or `None` for `started` or `exited`: lets `link.py` tell them
    apart without the private `_MessageKind`."""
    if event["kind"] != _MessageKind.DONE:
        return None
    return cast(_DoneEvent, event)["exit_code"]
