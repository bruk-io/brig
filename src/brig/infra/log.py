"""brig's one log envelope and its encoder (decision-0001 rule 14, TASK-0001 criterion 15).

Every line one of brig's own processes writes is one JSON object, these fields first and in this
order: `time` (RFC 3339, UTC, to the microsecond, `Z`), `level`, `source` (which of brig's
programs wrote it) and `event` (what happened), then the event's own fields. `encode` is the one
place a line is made, `decode` reads one back, and `write` is the one raw write of one to an fd.
The library itself writes no line: what it knows comes back to the embedder as data.

Standard library only, and it imports nothing of brig (the `brig-standalone-programs` gate): a
program brig ships as source (the egress proxy) has this module assembled in beside it, so it
writes exactly the envelope the library reads.
"""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

HEAD = ("time", "level", "source", "event")
"""The envelope's own fields, first in every line and in this order."""


class Level(StrEnum):
    """How much a line matters to whoever reads the log."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


type Field = str | int | float | bool | None
"""What one of an event's own fields may hold: a JSON scalar."""


@dataclass(frozen=True)
class Line:
    """One envelope line, read back: its head, and the event's own fields in their order."""

    time: datetime
    level: Level
    source: str
    event: str
    fields: frozendict[str, Field]


class LineUnreadable(Exception):
    """Raised by `decode` when a line is not one JSON object in brig's envelope: not JSON, its
    head missing, out of order or of the wrong kind, or a field that is not a JSON scalar."""

    def __init__(self, line: str, why: str) -> None:
        super().__init__(f"not a line in brig's log envelope ({why}): {line[:200]!r}")
        self.line = line
        self.why = why


def _stamp(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def encode(
    when: datetime, level: Level, source: str, event: str, fields: Mapping[str, Field]
) -> str:
    """One envelope line, ending in a newline: `when` (an aware time, written in UTC), `level`,
    `source` and `event`, then `fields` in their order. ASCII only, so a line's length in bytes
    is its length in characters.

    Raises:
        ValueError: `when` is naive, or a field is named like one of the envelope's own (`HEAD`).
    """
    if when.tzinfo is None:
        raise ValueError("a log line's time must be aware: pass datetime.now(UTC)")
    clash = sorted(set(HEAD) & set(fields))
    if clash:
        raise ValueError(f"an event's field may not be named like the envelope's own: {clash}")
    head: dict[str, Field] = {
        "time": _stamp(when),
        "level": level.value,
        "source": source,
        "event": event,
    }
    return json.dumps({**head, **fields}, ensure_ascii=True, separators=(",", ":")) + "\n"


def _scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def decode(text: str) -> Line:
    """The envelope line `text` (its trailing newline optional) as a `Line`.

    Raises:
        LineUnreadable: `text` is not one JSON object whose first fields are `HEAD`, in order,
            with an RFC 3339 UTC `time`, a known `level`, and string `source` and `event`, and
            whose every other field is a JSON scalar.
    """
    try:
        raw = json.loads(text)
    except ValueError as error:
        raise LineUnreadable(text, "not JSON") from error
    if not isinstance(raw, dict):
        raise LineUnreadable(text, "not a JSON object")
    if tuple(raw)[: len(HEAD)] != HEAD:
        raise LineUnreadable(text, f"its first fields are not {', '.join(HEAD)}, in order")
    stamp, level, source, event = (raw[name] for name in HEAD)
    if not all(isinstance(value, str) for value in (stamp, level, source, event)):
        raise LineUnreadable(text, "a head field is not a string")
    try:
        when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
        known = Level(level)
    except ValueError as error:
        raise LineUnreadable(text, "its time or level is not one the envelope writes") from error
    fields = {name: value for name, value in raw.items() if name not in HEAD}
    if not all(_scalar(value) for value in fields.values()):
        raise LineUnreadable(text, "an event field is not a JSON scalar")
    return Line(when, known, source, event, frozendict(fields))


def write(fd: int, line: str) -> None:
    """Write `line` whole to `fd`. A line no longer than `select.PIPE_BUF` reaches a pipe in one
    piece, never interleaved with another writer's. An `OSError` propagates."""
    data = line.encode("ascii")
    while data:
        data = data[os.write(fd, data) :]
