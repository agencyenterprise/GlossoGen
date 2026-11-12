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
from typing import Literal

import orjson
import pytest

from glossogen.models.event import MessageSent, core_event_types
from glossogen.models.event_base import EventBase
from glossogen.models.message import SimulationMessage
from glossogen.run_storage.run_archive import EventLocation, find_event_offset
from glossogen.runtime.event_bus import EventBus
from glossogen.runtime.event_logger import EventLogger, UndeclaredEventType
from glossogen.scenario_contract.event_types import loggable_event_types
from glossogen.scenarios.move_a_box.events import MoveABoxOperatorFinished
from glossogen.scenarios.move_a_box.scenario import MoveABoxScenario

PLATFORM_EVENTS = frozenset(core_event_types())
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
    logger = EventLogger(log_path=path, event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS)
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

    ``copy_run_at_event`` truncates a copy at an offset found earlier. If
    appending rewrote or reflowed earlier lines, every fork would silently cut
    in the wrong place.
    """
    path = tmp_path / "run.jsonl"
    logger = EventLogger(log_path=path, event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS)
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

    first = EventLogger(log_path=path, event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS)
    await first.open()
    await first.log(event=build_message(event_id="e0", round_number=1, content="first"))
    await first.close()

    resumed = EventLogger(log_path=path, event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS)
    await resumed.open_for_append()
    await resumed.log(event=build_message(event_id="e1", round_number=2, content="second"))
    await resumed.close()
    assert len(path.read_bytes().splitlines()) == 2

    restarted = EventLogger(log_path=path, event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS)
    await restarted.open()
    await restarted.close()
    assert path.read_bytes() == b""


async def test_append_to_missing_file_fails_loudly(tmp_path: Path, event_bus: EventBus) -> None:
    """Resuming a run whose log is gone raises rather than starting an empty one."""
    logger = EventLogger(
        log_path=tmp_path / "absent.jsonl", event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS
    )
    with pytest.raises(FileNotFoundError):
        await logger.open_for_append()


async def test_logging_before_open_fails_loudly(tmp_path: Path, event_bus: EventBus) -> None:
    """Writing to an unopened logger raises instead of dropping the event."""
    logger = EventLogger(
        log_path=tmp_path / "run.jsonl", event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS
    )
    with pytest.raises(RuntimeError):
        await logger.log(event=build_message(event_id="e0", round_number=1, content="m"))


async def test_concurrent_writes_never_interleave(tmp_path: Path, event_bus: EventBus) -> None:
    """Agents log concurrently; no line may be spliced into another.

    Every agent runner writes to one logger from its own task. Without the write
    lock a large payload can split across an await and produce a line that no
    longer parses. A corrupt ledger is unrecoverable: the offsets every fork
    depends on are computed from it.
    """
    path = tmp_path / "run.jsonl"
    logger = EventLogger(log_path=path, event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS)
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
    logger = EventLogger(
        log_path=tmp_path / "run.jsonl", event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS
    )
    await logger.open()
    await logger.log(event=build_message(event_id="e0", round_number=1, content="hello"))
    await logger.close()

    published = queue.get_nowait()
    assert published["event_id"] == "e0"
    message = published["message"]
    assert isinstance(message, dict)
    assert message["text"] == "hello"


class Undeclared(EventBase):
    """An event no scenario and no platform declares."""

    event_type: Literal["nobody_declares_this"] = "nobody_declares_this"


async def test_an_event_the_logger_was_not_built_to_accept_is_refused(
    tmp_path: Path, event_bus: EventBus
) -> None:
    """A run's reader skips what its scenario does not declare, so the writer refuses it.

    Nothing is written and nothing is published, so the log stays readable as it is.
    """
    path = tmp_path / "run.jsonl"
    queue = event_bus.create_subscriber_queue()
    logger = EventLogger(log_path=path, event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS)
    await logger.open()

    with pytest.raises(UndeclaredEventType, match="nobody_declares_this"):
        await logger.log(event=Undeclared(round_number=1))
    await logger.close()

    assert path.read_bytes() == b""
    assert queue.empty()


async def test_a_scenarios_declared_event_is_logged(tmp_path: Path, event_bus: EventBus) -> None:
    """The scenario's ``event_types()`` are what widen the platform's set."""
    path = tmp_path / "run.jsonl"
    logger = EventLogger(
        log_path=path,
        event_bus=event_bus,
        allowed_event_types=loggable_event_types(scenario_cls=MoveABoxScenario),
    )
    await logger.open()
    await logger.log(
        event=MoveABoxOperatorFinished(
            round_number=1,
            agent_id="operator_a",
            crate_id="operator_a#1",
            crate_marking="CR-1111",
            cell=(1, 1),
            bay=None,
            temperature=20,
            steps_used=3,
            reasoning=None,
        )
    )
    await logger.close()

    assert orjson.loads(path.read_bytes())["event_type"] == "move_a_box_operator_finished"


async def test_a_subclass_of_an_accepted_event_is_refused(
    tmp_path: Path, event_bus: EventBus
) -> None:
    """It would parse back as its parent, losing whatever it adds, so it must be declared itself."""

    class Narrowed(MessageSent):
        """A scenario's variant of a platform event."""

    logger = EventLogger(
        log_path=tmp_path / "run.jsonl", event_bus=event_bus, allowed_event_types=PLATFORM_EVENTS
    )
    await logger.open()
    narrowed = Narrowed.model_validate(
        build_message(event_id="e0", round_number=1, content="m").model_dump()
    )

    with pytest.raises(UndeclaredEventType, match="Narrowed"):
        await logger.log(event=narrowed)
    await logger.close()
