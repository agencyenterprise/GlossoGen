"""A model response is logged with the round and time it began in.

The runner logs a response once the next one starts or the cycle ends. A
response whose tool call waits for the next round would otherwise carry that
later round, and its reasoning would show under the wrong round.
"""

from pathlib import Path

import pytest

from glossogen.models.event import LLMResponseReceived, ToolCallInvoked, ToolResultReceived
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.testing.scripted_agent import EventGate, GatedTurn
from tests.scenarios.signal_game.signal_game_play import (
    build,
    end_round,
    play,
    read,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("signal_game")

NEXT_ROUND = {"wait_for": "next_round"}


def player_a_waits(event: dict[str, object]) -> bool:
    return (
        event["event_type"] == "tool_call_invoked"
        and event["agent_id"] == PLAYER_A
        and event["arguments"] == NEXT_ROUND
    )


async def test_a_response_whose_call_waits_into_the_next_round_keeps_its_own_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """player_a ends round 1 with a wait that only returns once round 2 starts.

    signal_game ends the round as soon as both players have called end_round, so
    player_b ends round 1 only after player_a's wait is in. Without that gate the
    round can end before player_a's wait response begins, and no response would
    wait across rounds. Where player_b's own wait lands is left to the scheduler;
    its response is checked against its call like every other.
    """
    scenario = build(preset_name="knobs_default", overrides={"round_count": 2})
    scripts: dict[str, list[GatedTurn]] = {
        PLAYER_A: [read(), end_round(), wait_for_next_round(), end_round(), wait_for_next_round()],
        PLAYER_B: [
            read(),
            EventGate(matches=player_a_waits, description="player_a waits for round 2"),
            end_round(),
            wait_for_next_round(),
            end_round(),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    invoked = {event.call_id: event for event in result.of_type(event_type=ToolCallInvoked)}
    returned = {event.call_id: event for event in result.of_type(event_type=ToolResultReceived)}
    responses = [
        response
        for response in result.of_type(event_type=LLMResponseReceived)
        if response.tool_calls
    ]
    assert responses
    for response in responses:
        for call in response.tool_calls:
            assert response.round_number == invoked[call.call_id].round_number, call
            assert response.timestamp <= invoked[call.call_id].timestamp, call
    first_wait = next(
        response
        for response in responses
        if response.agent_id == PLAYER_A and response.tool_calls[0].arguments == NEXT_ROUND
    )
    assert first_wait.round_number == 1
    assert returned[first_wait.tool_calls[0].call_id].round_number == 2
