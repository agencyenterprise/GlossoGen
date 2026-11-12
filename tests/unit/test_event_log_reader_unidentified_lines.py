"""An undeclared line with no `event_id` or `timestamp` is skipped, not fatal.

Every line the event logger writes carries both, so such a line was written by
hand or by something else. `UnrecognizedEvent` cannot hold it, and the reader
skips it and counts it in its warning rather than failing the whole run.
"""

import logging
from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.models.event import MessageSent, UnrecognizedEvent
from glossogen.run_storage.event_log_reader import load_events

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def write_log(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write raw JSONL rows, bypassing the event models."""
    path.write_bytes(b"".join(orjson.dumps(row) + b"\n" for row in rows))
    return path


def start_row() -> dict[str, Any]:
    """The `simulation_started` row naming a scenario that is not loaded."""
    return {
        "event_id": "start",
        "event_type": "simulation_started",
        "timestamp": FIXED_TIME,
        "run_id": "smoke/1780000000",
        "scenario_name": "smoke",
        "scenario_description": "d",
        "scenario_config": {},
        "channel_ids": ["link"],
        "provider": "anthropic",
    }


def message_row() -> dict[str, Any]:
    """A platform `message_sent` row after the foreign lines."""
    return {
        "event_id": "m1",
        "event_type": "message_sent",
        "timestamp": FIXED_TIME,
        "message": {
            "message_id": "m-m1",
            "channel_id": "link",
            "sender_agent_id": "agent_a",
            "sender_display_name": "Agent A",
            "text": "still read",
            "timestamp": FIXED_TIME,
        },
        "token_count": 10,
    }


@pytest.mark.parametrize("missing", ["event_id", "timestamp"])
async def test_a_line_missing_its_id_or_timestamp_is_skipped_and_counted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, missing: str
) -> None:
    """The rest of the run reads back; the warning counts the skipped line by type."""
    foreign = {"event_id": "x", "event_type": "hand_written", "timestamp": FIXED_TIME}
    del foreign[missing]
    log = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            start_row(),
            foreign,
            {"event_id": "k", "event_type": "kept_one", "timestamp": FIXED_TIME},
            message_row(),
        ],
    )

    with caplog.at_level(logging.WARNING):
        events = await load_events(log_path=log)

    assert [event.event_id for event in events] == ["start", "k", "m1"]
    assert isinstance(events[1], UnrecognizedEvent)
    assert isinstance(events[2], MessageSent)
    assert "Skipped 1 more line(s)" in caplog.text
    assert "'hand_written': 1" in caplog.text
