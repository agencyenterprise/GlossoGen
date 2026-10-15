"""A model response is logged with the round and time it began in.

The runner logs a response once the next one starts or the cycle ends. A
response whose tool call waits for the next round would otherwise carry that
later round, and its reasoning would show under the wrong round.
"""

from pathlib import Path

import pytest

from glossogen.models.event import LLMResponseReceived, ToolCallInvoked
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.testing.scripted_agent import ScriptedTurn
from tests.scenarios.signal_game.signal_game_play import build, finish, play, read

pytestmark = pytest.mark.xdist_group("signal_game")


async def test_a_response_whose_call_waits_into_the_next_round_keeps_its_own_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each player finishes round 1 with a wait that only returns once round 2 starts."""
    scenario = build(preset_name="knobs_default", overrides={"round_count": 2})
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), finish(), finish()],
        PLAYER_B: [read(), finish(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    invoked = {event.call_id: event for event in result.of_type(event_type=ToolCallInvoked)}
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
    first_finishes = [
        response
        for response in responses
        if response.tool_calls[0].arguments == {"wait_for": "next_round"}
        and response.round_number == 1
    ]
    assert {response.agent_id for response in first_finishes} == {PLAYER_A, PLAYER_B}
