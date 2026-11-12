"""A line of an event type no loaded scenario declares reads back, and writes back unchanged."""

from pathlib import Path
from typing import Any

import orjson
import pytest
from pydantic import ValidationError

from glossogen.models.event import UnrecognizedEvent
from glossogen.run_storage.event_log_reader import load_events

START_LINE = (
    b'{"event_id":"start","timestamp":"2026-01-01T00:00:00Z","round_number":0,'
    b'"event_type":"simulation_started","run_id":"gone_scenario/1","scenario_name":'
    b'"gone_scenario","scenario_description":"","channel_ids":["link"],'
    b'"scenario_config":{},"provider":"anthropic"}'
)

# Keys out of the platform's usual order, a float that must keep its digits,
# non-ASCII text, nested lists and objects, a null, and no round_number.
UNRECOGNIZED_LINES = [
    b'{"event_type":"gone_board_dealt","timestamp":"2026-01-01T00:00:01.123456+00:00",'
    b'"event_id":"e1","board":[[1,2],[3,null]],"weights":{"b":0.1,"a":2.5e-7},'
    b'"note":"caf\xc3\xa9 \xe2\x9c\x93","round_number":1}',
    b'{"event_id":"e2","timestamp":"2026-01-01T00:00:02+00:00",'
    b'"event_type":"gone_round_scored","score":-0.0,"flags":[true,false]}',
]


def _write(path: Path, lines: list[bytes]) -> Path:
    path.write_bytes(b"".join(line + b"\n" for line in lines))
    return path


async def test_a_line_the_logger_wrote_serializes_back_byte_for_byte(tmp_path: Path) -> None:
    """The lines are in orjson's spelling, which is how the event logger writes every line."""
    log = _write(path=tmp_path / "gone_scenario.jsonl", lines=[START_LINE, *UNRECOGNIZED_LINES])

    _, *unrecognized = await load_events(log_path=log)

    assert all(isinstance(event, UnrecognizedEvent) for event in unrecognized)
    written = [orjson.dumps(event.model_dump(mode="json")) for event in unrecognized]
    assert written == UNRECOGNIZED_LINES
    assert [event.model_dump() for event in unrecognized] == [
        orjson.loads(line) for line in UNRECOGNIZED_LINES
    ]


async def test_an_unrecognized_event_reads_like_any_event(tmp_path: Path) -> None:
    log = _write(path=tmp_path / "gone_scenario.jsonl", lines=[START_LINE, *UNRECOGNIZED_LINES])

    _, dealt, scored = await load_events(log_path=log)

    assert isinstance(dealt, UnrecognizedEvent)
    assert isinstance(scored, UnrecognizedEvent)
    assert (dealt.event_id, dealt.event_type, dealt.round_number) == ("e1", "gone_board_dealt", 1)
    assert dealt.timestamp.microsecond == 123456
    # The second line has no round_number: it is given the running round, which
    # is still 0 here, and its payload does not gain one.
    assert scored.round_number == 0
    assert "round_number" not in scored.payload


@pytest.mark.parametrize("missing", ["event_id", "timestamp"])
def test_a_line_without_the_fields_every_event_carries_does_not_validate(missing: str) -> None:
    record: dict[str, Any] = {
        "event_id": "e1",
        "timestamp": "2026-01-01T00:00:00Z",
        "event_type": "gone_board_dealt",
    }
    del record[missing]

    with pytest.raises(ValidationError):
        UnrecognizedEvent.from_record(record=record, round_number=0)


async def test_a_line_spelled_otherwise_serializes_back_to_an_equal_object(tmp_path: Path) -> None:
    """Only the decoded object is kept, so other whitespace and escapes come back respelled."""
    line = (
        b'{ "event_id": "e1", "timestamp": "2026-01-01T00:00:01+00:00",'
        b' "event_type": "gone_round_scored", "score": 1e0, "text": "\\u0061" }'
    )
    log = _write(path=tmp_path / "gone_scenario.jsonl", lines=[START_LINE, line])

    _, scored = await load_events(log_path=log)

    assert isinstance(scored, UnrecognizedEvent)
    assert scored.model_dump(mode="json") == orjson.loads(line)
    assert list(scored.model_dump(mode="json")) == list(orjson.loads(line))
