"""Gateway tests for `infra/log.py`, brig's one log envelope and its encoder (TASK-0001
criterion 15, TASK-0001.37): a line is one JSON object with `time`, `level`, `source` and
`event` first, in that order, then the event's own fields; `decode` reads back exactly what
`encode` wrote and refuses what it would not write; `write` puts a line on a pipe whole. One
infra module against the real `os` (decision-0001 rule 4)."""

import json
import os
from datetime import UTC, datetime, timedelta, timezone

import pytest

from brig.infra import log

_WHEN = datetime(2026, 11, 4, 5, 6, 7, 123456, tzinfo=UTC)


def test_a_line_is_the_head_in_order_then_the_events_fields() -> None:
    line = log.encode(
        _WHEN, log.Level.WARNING, "egress-proxy", "egress-decision", {"b": 1, "a": "x"}
    )

    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert list(json.loads(line)) == ["time", "level", "source", "event", "b", "a"]
    assert json.loads(line)["time"] == "2026-11-04T05:06:07.123456Z"
    assert json.loads(line)["level"] == "warning"


def test_an_aware_time_in_another_zone_is_written_in_utc() -> None:
    elsewhere = _WHEN.astimezone(timezone(timedelta(hours=-5)))

    line = log.encode(elsewhere, log.Level.INFO, "s", "e", {})

    assert json.loads(line)["time"] == "2026-11-04T05:06:07.123456Z"


def test_decode_reads_back_what_encode_wrote() -> None:
    fields: dict[str, log.Field] = {"seq": 3, "host": "hé", "ok": True, "gone": None, "ratio": 0.5}

    read = log.decode(log.encode(_WHEN, log.Level.INFO, "egress-proxy", "egress-decision", fields))

    assert read == log.Line(
        _WHEN, log.Level.INFO, "egress-proxy", "egress-decision", frozendict(fields)
    )


def test_a_line_is_ascii_whatever_its_fields_hold() -> None:
    assert log.encode(_WHEN, log.Level.INFO, "s", "e", {"host": "é中"}).isascii()


@pytest.mark.parametrize("name", log.HEAD)
def test_a_field_named_like_the_envelopes_own_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="envelope"):
        log.encode(_WHEN, log.Level.INFO, "s", "e", {name: "x"})


def test_a_naive_time_is_refused() -> None:
    with pytest.raises(ValueError, match="aware"):
        log.encode(datetime(2026, 11, 4), log.Level.INFO, "s", "e", {})


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[1, 2]",
        '{"level": "info", "time": "2026-11-04T05:06:07.123456Z", "source": "s", "event": "e"}',
        '{"time": "yesterday", "level": "info", "source": "s", "event": "e"}',
        '{"time": "2026-11-04T05:06:07.123456Z", "level": "loud", "source": "s", "event": "e"}',
        '{"time": "2026-11-04T05:06:07.123456Z", "level": "info", "source": 1, "event": "e"}',
        '{"time": "2026-11-04T05:06:07.123456Z", "level": "info", "source": "s", "event": "e", '
        '"x": [1]}',
    ],
)
def test_decode_refuses_what_encode_would_not_write(text: str) -> None:
    with pytest.raises(log.LineUnreadable) as raised:
        log.decode(text)

    assert raised.value.line == text


def test_write_puts_a_line_on_a_pipe_whole() -> None:
    line = log.encode(_WHEN, log.Level.INFO, "s", "e", {"pad": "x" * 3000})
    read_end, write_end = os.pipe()
    try:
        log.write(write_end, line)
        os.close(write_end)
        write_end = -1
        data = b""
        while chunk := os.read(read_end, 65536):
            data += chunk
    finally:
        os.close(read_end)
        if write_end != -1:
            os.close(write_end)

    assert data.decode("ascii") == line
