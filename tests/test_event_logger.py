"""Tests for the JSONL event log, which is the canonical state ledger.

Fork, resume, replace-agent and cross-run all locate an event by scanning this
file for a byte offset and truncating there. That makes two properties
load-bearing rather than incidental: a line, once written, is never rewritten,
and the offset of an event does not move when later events are appended. Both
are asserted here directly rather than inferred from the code.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import orjson
import pytest

from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.models.event import MessageSent
from glossogen.models.message import SimulationMessage
from glossogen.run_archive import EventLocation, find_event_offset

FIXED_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def build_message(*, event_id: str, round_number: int, content: str) -> MessageSent:
    """Build a MessageSent carrying an identifiable payload."""
    return MessageSent(
        event_id=event_id,
        timestamp=FIXED_TIME,
        round_number=round_number,
        message=SimulationMessage(
            message_id=f"m-{event_id}",
            channel_id="link",
            sender_agent_id="agent_a",
            sender_display_name="Agent A",
            text=content,
            timestamp=FIXED_TIME,
            round_number=round_number,
        ),
        token_count=len(content),
    )


def locate(location: EventLocation | None) -> EventLocation:
    """Assert an event was found, narrowing away the None the scan may return."""
    assert location is not None
    return location


async def log_all(*, logger: EventLogger, events: list[MessageSent]) -> None:
    """Write every event through the logger."""
    for event in events:
        await logger.log(event=event)


async def test_writes_one_json_line_per_event(tmp_path: Path, event_bus: EventBus) -> None:
    """Each logged event is exactly one parseable line, in the order written."""
    path = tmp_path / "run.jsonl"
    logger = EventLogger(log_path=path, event_bus=event_bus)
    await logger.open()
    await log_all(
        logger=logger,
        events=[build_message(event_id=f"e{i}", round_number=i, content=f"m{i}") for i in range(5)],
    )
    await logger.close()

    lines = path.read_bytes().splitlines()
    assert len(lines) == 5
    assert [orjson.loads(line)["event_id"] for line in lines] == ["e0", "e1", "e2", "e3", "e4"]


async def test_event_offsets_do_not_move_when_more_events_arrive(
    tmp_path: Path, event_bus: EventBus
) -> None:
    """An event's byte offset is stable for the life of the run.

    This is what makes ``copy_run_at_event`` safe: it truncates a copy at an
    offset found earlier. If appending rewrote or reflowed earlier lines, every
    fork would silently cut in the wrong place.
    """
    path = tmp_path / "run.jsonl"
    logger = EventLogger(log_path=path, event_bus=event_bus)
    await logger.open()

    await log_all(
        logger=logger,
        events=[build_message(event_id=f"e{i}", round_number=i, content=f"m{i}") for i in range(3)],
    )
    offset_after_three = locate(await find_event_offset(log_path=path, event_id="e1"))
    prefix_after_three = path.read_bytes()[: offset_after_three.end_offset]

    await log_all(
        logger=logger,
        events=[
            build_message(event_id=f"e{i}", round_number=i, content=f"m{i}") for i in range(3, 9)
        ],
    )
    await logger.close()

    offset_after_nine = locate(await find_event_offset(log_path=path, event_id="e1"))
    assert offset_after_nine.end_offset == offset_after_three.end_offset
    # The truncated prefix is byte-identical, which is what a fork copies.
    assert path.read_bytes()[: offset_after_nine.end_offset] == prefix_after_three


async def test_open_truncates_but_append_preserves(tmp_path: Path, event_bus: EventBus) -> None:
    """``open`` starts a clean run; ``open_for_append`` continues one."""
    path = tmp_path / "run.jsonl"

    first = EventLogger(log_path=path, event_bus=event_bus)
    await first.open()
    await first.log(event=build_message(event_id="e0", round_number=1, content="first"))
    await first.close()

    resumed = EventLogger(log_path=path, event_bus=event_bus)
    await resumed.open_for_append()
    await resumed.log(event=build_message(event_id="e1", round_number=2, content="second"))
    await resumed.close()
    assert len(path.read_bytes().splitlines()) == 2

    restarted = EventLogger(log_path=path, event_bus=event_bus)
    await restarted.open()
    await restarted.close()
    assert path.read_bytes() == b""


async def test_append_to_missing_file_fails_loudly(tmp_path: Path, event_bus: EventBus) -> None:
    """Resuming a run whose log is gone raises rather than starting an empty one."""
    logger = EventLogger(log_path=tmp_path / "absent.jsonl", event_bus=event_bus)
    with pytest.raises(FileNotFoundError):
        await logger.open_for_append()


async def test_logging_before_open_fails_loudly(tmp_path: Path, event_bus: EventBus) -> None:
    """Writing to an unopened logger raises instead of dropping the event."""
    logger = EventLogger(log_path=tmp_path / "run.jsonl", event_bus=event_bus)
    with pytest.raises(RuntimeError):
        await logger.log(event=build_message(event_id="e0", round_number=1, content="m"))


async def test_concurrent_writes_never_interleave(tmp_path: Path, event_bus: EventBus) -> None:
    """Agents log concurrently; no line may be spliced into another.

    Every agent runner writes to one logger from its own task. Without the
    write lock a large payload can be split across an await, producing a line
    that no longer parses — and a corrupt ledger is unrecoverable, because the
    offsets every fork depends on are computed from it.
    """
    path = tmp_path / "run.jsonl"
    logger = EventLogger(log_path=path, event_bus=event_bus)
    await logger.open()

    # Payloads large enough that a partial write would be visible.
    events = [
        build_message(event_id=f"e{i}", round_number=i, content=f"{i}-" + "x" * 20_000)
        for i in range(40)
    ]
    await asyncio.gather(*(logger.log(event=event) for event in events))
    await logger.close()

    lines = path.read_bytes().splitlines()
    assert len(lines) == 40
    decoded = [orjson.loads(line) for line in lines]
    assert {row["event_id"] for row in decoded} == {f"e{i}" for i in range(40)}
    for row in decoded:
        index = row["event_id"][1:]
        assert row["message"]["text"] == f"{index}-" + "x" * 20_000


async def test_logged_events_reach_the_event_bus(tmp_path: Path, event_bus: EventBus) -> None:
    """Live SSE viewers see an event only if the logger publishes it."""
    queue = event_bus.create_subscriber_queue()
    logger = EventLogger(log_path=tmp_path / "run.jsonl", event_bus=event_bus)
    await logger.open()
    await logger.log(event=build_message(event_id="e0", round_number=1, content="hello"))
    await logger.close()

    published = queue.get_nowait()
    assert published["event_id"] == "e0"
    message = published["message"]
    assert isinstance(message, dict)
    assert message["text"] == "hello"
