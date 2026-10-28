"""Tests for reading a finished run back off disk.

Everything downstream of a run enters through here: `evaluate`, the web server,
fork, resume, and every metric. A run is only as recoverable as this module
makes it, and the parts that need pinning are the ones that reconstruct data the
JSONL does not literally carry.

The round backfill is the main one. `round_number` was promoted to the event
base after runs had already been written, so older logs have events without it
and this loader infers each from the most recent `round_advanced`. Every
per-round metric buckets on that inferred value.
"""

import logging
from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.evaluation.log_reader import (
    extract_agent_configs,
    extract_scenario_config,
    extract_simulation_id,
    load_events,
)
from glossogen.models.event import MessageSent, RoundAdvanced

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def write_log(*, path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write raw JSONL rows, bypassing the event models.

    Deliberately raw: these tests are about what the loader does with logs it
    did not write, including ones written by an older version of the platform.
    """
    path.write_bytes(b"".join(orjson.dumps(row) + b"\n" for row in rows))
    return path


def base_row(*, event_id: str, event_type: str, **extra: Any) -> dict[str, Any]:
    """Build one raw event row with no `round_number`."""
    return {"event_id": event_id, "event_type": event_type, "timestamp": FIXED_TIME, **extra}


def message_row(*, event_id: str, text: str) -> dict[str, Any]:
    """A `message_sent` row whose nested message also lacks a round."""
    return base_row(
        event_id=event_id,
        event_type="message_sent",
        message={
            "message_id": f"m-{event_id}",
            "channel_id": "link",
            "sender_agent_id": "agent_a",
            "sender_display_name": "Agent A",
            "text": text,
            "timestamp": FIXED_TIME,
        },
        token_count=len(text),
    )


def registration_row(*, agent_id: str, model: str) -> dict[str, Any]:
    """An `agent_registered` row as the runtime writes it."""
    return base_row(
        event_id=f"reg-{agent_id}",
        event_type="agent_registered",
        agent_id=agent_id,
        role_name=agent_id.replace("_", " ").title(),
        system_prompt=f"You are {agent_id}.",
        channel_ids=["link"],
        tool_names=["send_message"],
        model=model,
        provider="anthropic",
        max_tokens=16384,
    )


async def test_events_before_the_first_round_belong_to_round_zero(tmp_path: Path) -> None:
    """Startup events precede round 1 and must not be attributed to it.

    Counting `agent_registered` into round 1 would inflate every per-round
    total at the one round most likely to be compared across runs.
    """
    path = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            base_row(
                event_id="start",
                event_type="simulation_started",
                run_id="smoke/1780000000",
                scenario_name="smoke",
                scenario_description="d",
                scenario_config={},
                channel_ids=["link"],
                provider="anthropic",
            ),
            registration_row(agent_id="agent_a", model="claude-sonnet-4-6"),
        ],
    )
    events = await load_events(log_path=path)
    assert [event.round_number for event in events] == [0, 0]


async def test_a_missing_round_is_inferred_from_the_last_advance(tmp_path: Path) -> None:
    """Each event inherits the round that was open when it was written."""
    path = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            base_row(event_id="adv1", event_type="round_advanced", round_number=1, trigger="start"),
            message_row(event_id="m1", text="first"),
            base_row(event_id="adv2", event_type="round_advanced", round_number=2, trigger="idle"),
            message_row(event_id="m2", text="second"),
            message_row(event_id="m3", text="third"),
        ],
    )
    events = await load_events(log_path=path)
    assert [event.round_number for event in events] == [1, 1, 2, 2, 2]


async def test_the_nested_message_gets_the_round_too(tmp_path: Path) -> None:
    """Message-level metrics read the round off the message, not the event.

    The two are separate fields, and a message left at round 0 lands in a
    bucket no round owns.
    """
    path = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            base_row(event_id="adv1", event_type="round_advanced", round_number=4, trigger="idle"),
            message_row(event_id="m1", text="in round four"),
        ],
    )
    events = await load_events(log_path=path)
    sent = events[1]
    assert isinstance(sent, MessageSent)
    assert sent.round_number == 4
    assert sent.message.round_number == 4


async def test_an_explicit_round_is_left_alone(tmp_path: Path) -> None:
    """Backfill fills gaps; it never overrides what the writer recorded."""
    path = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            base_row(event_id="adv1", event_type="round_advanced", round_number=3, trigger="idle"),
            message_row(event_id="m1", text="tagged") | {"round_number": 99},
        ],
    )
    events = await load_events(log_path=path)
    assert events[1].round_number == 99


async def test_blank_lines_are_skipped(tmp_path: Path) -> None:
    """A trailing newline is normal and must not fail the read."""
    path = tmp_path / "run.jsonl"
    path.write_bytes(
        orjson.dumps(
            base_row(event_id="adv1", event_type="round_advanced", round_number=1, trigger="start")
        )
        + b"\n\n"
    )
    events = await load_events(log_path=path)
    assert len(events) == 1
    assert isinstance(events[0], RoundAdvanced)


async def test_agent_configs_are_rebuilt_from_their_registrations(tmp_path: Path) -> None:
    """Evaluation reconstructs who ran under what without the original config."""
    path = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            registration_row(agent_id="agent_a", model="claude-sonnet-4-6"),
            registration_row(agent_id="agent_b", model="gpt-5.4"),
            message_row(event_id="m1", text="hello"),
        ],
    )
    configs = extract_agent_configs(events=await load_events(log_path=path))
    assert [config.agent_id for config in configs] == ["agent_a", "agent_b"]
    assert [config.model for config in configs] == ["claude-sonnet-4-6", "gpt-5.4"]


async def test_rebuilt_configs_report_the_default_compaction(tmp_path: Path) -> None:
    """`agent_registered` records no compaction, so this field is not recovered.

    Pinned because the value looks authoritative and is not. Anything that
    needs to know what compaction a run used has to read the
    `context_compacted` events instead. Documented in the module, asserted here
    so a future change to the event has to come past this test.
    """
    path = write_log(
        path=tmp_path / "run.jsonl",
        rows=[registration_row(agent_id="agent_a", model="claude-sonnet-4-6")],
    )
    configs = extract_agent_configs(events=await load_events(log_path=path))
    assert configs[0].compaction.enabled is False


async def test_the_simulation_id_and_config_come_off_the_start_event(tmp_path: Path) -> None:
    """The knobs a run used are recoverable only from what it logged at launch."""
    knobs = {"round_count": 15, "max_round_duration_seconds": 120.0}
    path = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            base_row(
                event_id="sim-42",
                event_type="simulation_started",
                run_id="smoke/1780000000",
                scenario_name="smoke",
                scenario_description="d",
                scenario_config=knobs,
                channel_ids=["link"],
                provider="anthropic",
            )
        ],
    )
    events = await load_events(log_path=path)
    assert extract_simulation_id(events=events) == "sim-42"
    assert extract_scenario_config(events=events) == knobs


async def test_a_log_with_no_start_event_raises(tmp_path: Path) -> None:
    """A truncated or hand-edited log fails loudly rather than defaulting."""
    path = write_log(
        path=tmp_path / "run.jsonl",
        rows=[message_row(event_id="m1", text="orphan")],
    )
    events = await load_events(log_path=path)
    with pytest.raises(ValueError):
        extract_simulation_id(events=events)
    with pytest.raises(ValueError):
        extract_scenario_config(events=events)


async def test_an_event_no_class_declares_is_skipped_and_counted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A run naming an event this build has no class for still reads back.

    Two ways a log does that: a scenario that is not installed on this checkout
    wrote it, or the event was renamed after the run. Either way one dead name
    used to cost the whole run, because the discriminated union refuses a tag it
    does not know and the reader let that escape to the caller.
    """
    log = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            base_row(event_id="a", event_type="round_advanced", round_number=1, trigger="start"),
            base_row(event_id="b", event_type="a_scenario_that_is_not_installed"),
            base_row(event_id="c", event_type="an_event_renamed_since_the_run"),
            base_row(event_id="d", event_type="a_scenario_that_is_not_installed"),
            base_row(event_id="e", event_type="round_advanced", round_number=2, trigger="idle"),
        ],
    )

    with caplog.at_level(logging.WARNING):
        events = await load_events(log_path=log)

    assert [event.event_id for event in events] == ["a", "e"]
    assert "a_scenario_that_is_not_installed" in caplog.text
    assert "an_event_renamed_since_the_run" in caplog.text


async def test_a_skipped_event_still_advances_the_round_backfill(tmp_path: Path) -> None:
    """Skipping an unreadable event must not shift the rounds of the readable ones.

    The backfill infers each event's round from the last `round_advanced` it
    walked past, so a reader that skipped a row before observing it would file
    every later event under the wrong round, and every per-round metric with it.
    """
    log = write_log(
        path=tmp_path / "run.jsonl",
        rows=[
            base_row(event_id="a", event_type="round_advanced", round_number=4, trigger="idle"),
            base_row(event_id="b", event_type="no_class_declares_this"),
            message_row(event_id="m1", text="after the skipped row"),
        ],
    )

    events = await load_events(log_path=log)

    sent = next(event for event in events if isinstance(event, MessageSent))
    assert sent.round_number == 4, "the skipped row must not reset the running round"
