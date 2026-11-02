"""The closing question under ``describe_protocol_at_end``: what move_a_box asks once a run is over.

The runner sends it; the scenario only words it. The tests check that the
question does not mention temperature, the readout or any action, that it is
absent with the knob off, and that each operator's answer is logged.
"""

from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import AgentRegistered, ClosingPromptAnswered
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn
from tests.scenarios.move_a_box.move_a_box_play import (
    ONE_ROUND,
    build,
    finish,
    play,
    read,
    to_shared_bay,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")

ONE_ROUND_ASKED: dict[str, Any] = {**ONE_ROUND, "describe_protocol_at_end": True}


def test_the_question_asks_about_a_convention_without_naming_the_reading() -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND_ASKED)
    prompts = scenario.runner_prompts(agent_id=OPERATOR_A)
    assert prompts is not None
    assert prompts.closing is not None
    question = prompts.closing.lower()
    assert "settle on any way of telling each other something" in question
    for word in ("temperature", "reading", "readout", "haul", "ice"):
        assert word not in question


def test_with_the_knob_off_there_is_no_closing_question() -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    prompts = scenario.runner_prompts(agent_id=OPERATOR_A)
    assert prompts is not None
    assert prompts.closing is None


async def test_each_operator_answers_once_the_run_is_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND_ASKED)
    answers = {OPERATOR_A: "cart meant the shared bay", OPERATOR_B: "we never agreed on anything"}
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [
            read(),
            *to_shared_bay(method="cart"),
            finish(),
            wait_for_next_round(),
            SayTurn(text="The shift is over."),
            SayTurn(text=answer),
        ]
        for agent_id, answer in answers.items()
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    prompts = scenario.runner_prompts(agent_id=OPERATOR_A)
    assert prompts is not None
    logged = {event.agent_id: event for event in result.of_type(event_type=ClosingPromptAnswered)}
    assert {agent_id: event.answer for agent_id, event in logged.items()} == answers
    assert all(event.prompt == prompts.closing for event in logged.values())
    # The registration records the question, so the run says what was asked.
    for registration in result.of_type(event_type=AgentRegistered):
        assert registration.runner_prompts is not None
        assert registration.runner_prompts.closing == prompts.closing
