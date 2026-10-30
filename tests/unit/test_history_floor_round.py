"""``history_floor_round`` windows a replaced seat that belongs to no channel.

Channel floors only reach the non-channel tools through a ``FromRound`` entry,
so a seat in a scenario without channels (signal_game plays through ``move``
alone) kept its predecessor's whole tool-call record. The seat floor drops
those calls by round directly, and replace-agent checks it like a channel
floor.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import orjson
import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from glossogen.models.event import (
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.run_derivation.replace_agent import ReplaceAgentRequest, prepare_replace_agent_run
from glossogen.run_derivation.replace_manifest import REPLACE_MANIFEST_FILENAME
from glossogen.run_replay.message_history_builder import build_message_history
from glossogen.run_replay.resume_state_loader import read_replace_manifest_info
from glossogen.runners.communication_protocol import platform_runner_prompts

_AGENT = "player"


def _move_turn(round_number: int, call_id: str, timestamp: datetime) -> list[SimulationEvent]:
    """One LLM cycle in ``round_number`` making a single ``move`` call."""
    arguments: dict[str, object] = {"directions": ["up"], "reasoning": "Scripted move."}
    events: list[SimulationEvent] = [
        ToolCallInvoked(
            round_number=round_number,
            agent_id=_AGENT,
            call_id=call_id,
            tool_name="move",
            arguments=arguments,
        ),
        ToolResultReceived(
            round_number=round_number,
            agent_id=_AGENT,
            tool_name="move",
            call_id=call_id,
            arguments=arguments,
            result="moved",
        ),
        LLMResponseReceived(
            round_number=round_number,
            agent_id=_AGENT,
            text="",
            tool_calls=[ToolCallRequest(call_id=call_id, tool_name="move", arguments=arguments)],
            stop_reason=StopReason.TOOL_USE,
            usage=TokenUsage(
                input_tokens=1,
                output_tokens=1,
                reasoning_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        ),
    ]
    stamped: list[SimulationEvent] = []
    for offset, event in enumerate(events):
        assert isinstance(event, EventBase)
        stamped.append(
            event.model_copy(update={"timestamp": timestamp + timedelta(milliseconds=offset)})
        )
    return stamped


def _surviving_call_ids(history_floor_round: int | None) -> set[str]:
    """Rebuild a channel-less seat's history and collect the call ids it keeps."""
    start = datetime(2026, 10, 1, tzinfo=UTC)
    events: list[SimulationEvent] = [
        SimulationStarted(
            round_number=0,
            timestamp=start,
            run_id="signal/1",
            scenario_name="signal",
            scenario_description="",
            channel_ids=[],
            scenario_config={"round_count": 3},
            provider="anthropic",
        ),
        *_move_turn(round_number=1, call_id="r1", timestamp=start + timedelta(seconds=1)),
        *_move_turn(round_number=2, call_id="r2", timestamp=start + timedelta(seconds=2)),
        *_move_turn(round_number=3, call_id="r3", timestamp=start + timedelta(seconds=3)),
    ]
    history = build_message_history(
        events=events,
        agent_id=_AGENT,
        system_prompt="play",
        runner_prompts=platform_runner_prompts(role_name="player"),
        target_timestamp=events[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=True,
        channel_visibility={},
        history_floor_round=history_floor_round,
        filter_below_round=None,
        split_parallel_tool_calls=False,
    )
    return {
        part.tool_call_id
        for message in history
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }


def test_a_seat_with_no_channels_keeps_only_calls_from_the_floor_round_on() -> None:
    assert _surviving_call_ids(history_floor_round=2) == {"r2", "r3"}


def test_a_floor_past_every_recorded_round_leaves_no_prior_calls() -> None:
    assert _surviving_call_ids(history_floor_round=4) == set()


def test_no_floor_keeps_the_whole_record() -> None:
    assert _surviving_call_ids(history_floor_round=None) == {"r1", "r2", "r3"}


def _request(
    tmp_path: Path, replaced_agent_id: str | None, history_floor_round: int | None
) -> ReplaceAgentRequest:
    """A request against a source that does not exist, so only validation can answer."""
    replacing = replaced_agent_id is not None
    model: str | None = None
    provider: str | None = None
    visible: list[str] | None = None
    if replacing:
        model = "claude-haiku-5-5"
        provider = "anthropic"
        visible = []
    return ReplaceAgentRequest(
        source_run_dir=tmp_path / "missing",
        scenario_name="smoke",
        after_round=9,
        rounds_after=10,
        replaced_agent_id=replaced_agent_id,
        model=model,
        provider=provider,
        knobs=None,
        channels_with_visible_history=visible,
        channel_history_floors={},
        history_floor_round=history_floor_round,
        runs_dir=tmp_path / "runs",
    )


async def test_a_floor_past_the_entry_round_is_refused(tmp_path: Path) -> None:
    request = _request(tmp_path=tmp_path, replaced_agent_id="player", history_floor_round=11)

    with pytest.raises(ValueError, match=r"history_floor_round=11 must satisfy"):
        await prepare_replace_agent_run(request=request)


async def test_a_fork_with_no_replaced_seat_refuses_a_floor(tmp_path: Path) -> None:
    request = _request(tmp_path=tmp_path, replaced_agent_id=None, history_floor_round=5)

    with pytest.raises(ValueError, match="history_floor_round"):
        await prepare_replace_agent_run(request=request)


def test_a_manifest_written_before_the_seat_floor_loads_with_none(tmp_path: Path) -> None:
    manifest: dict[str, object] = {
        "source_run_id": "signal/1",
        "source_run_dir": "/runs/signal/1",
        "round_start": 10,
        "rounds_after_swap": 9,
        "target_event_id": "e-1",
        "replaced_agent_id": "player",
        "replacement_model": "claude-haiku-5-5",
        "replacement_provider": "anthropic",
        "channels_with_visible_history": [],
        "blocked_tool_call_channels": [],
        "channel_history_floors": {},
        "replaced_at": 1_700_000_000.0,
    }
    (tmp_path / REPLACE_MANIFEST_FILENAME).write_bytes(orjson.dumps(manifest))

    info = read_replace_manifest_info(run_dir=tmp_path)

    assert info is not None
    assert info.history_floor_round is None
