"""``send_message`` refuses text that is empty or only whitespace.

An empty message costs no characters on a scored channel but still tells the
other members who sent it, so agents used one as a free signal.
"""

from pathlib import Path

import pytest

from glossogen.models.event import MessageSent, ToolResultReceived
from glossogen.testing.scripted_agent import SayTurn, ToolTurn
from glossogen.testing.simulation_harness import never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)


def send(text: str) -> ToolTurn:
    return ToolTurn(
        tool_name="send_message",
        args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
    )


async def test_empty_and_whitespace_text_reach_the_agent_as_an_error_and_post_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_simulation(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
        ),
        scripts={
            FIRST_AGENT_ID: [
                send(text=""),
                send(text=" \n\t"),
                send(text="ok"),
                SayTurn(text="done"),
            ],
            SECOND_AGENT_ID: [SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    answers = [
        e.result
        for e in result.of_type(event_type=ToolResultReceived)
        if e.agent_id == FIRST_AGENT_ID and e.tool_name == "send_message"
    ]
    assert len(answers) == 3
    assert "text is empty" in answers[0]
    assert "text is empty" in answers[1]
    sent = [
        e.message.text
        for e in result.of_type(event_type=MessageSent)
        if e.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert sent == ["ok"]
