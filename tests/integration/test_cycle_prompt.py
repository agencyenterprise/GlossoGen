"""A scenario's cycle prompt through ``take_cycle_prompt``, outside signal_game.

The smoke scenario hands the first agent one prompt before its first model
request. The runner ends that cycle without sending anything, and the agent's
first request holds the initial prompt followed by the cycle prompt. The run
logs ``cycle_prompt_sent`` once, and a scenario that returns None leaves the
cycle alone.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from glossogen.models.event import CyclePromptSent
from glossogen.scenario_contract.platform_runner_prompts import INITIAL_PROMPT
from glossogen.testing import simulation_harness
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    RECORD_TOOL_NAME,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)
from tests.fakes.flaky_model import BUILD_SCRIPTED_MODEL, FlakyModelRecorder

CYCLE_PROMPT = "The scenario opens your next cycle with this message."
RECORD_TURN = ToolTurn(tool_name=RECORD_TOOL_NAME, args={"finding": "cycle prompt probe"})


class PromptingSmokeScenario(SmokeScenario):
    """The smoke scenario, handing the first agent one cycle prompt before any model request."""

    def __init__(self, knobs: SmokeKnobs) -> None:
        super().__init__(knobs=knobs)
        self.prompt_taken = False

    def take_cycle_prompt(self, agent_id: str) -> str | None:
        if agent_id != FIRST_AGENT_ID or self.prompt_taken:
            return None
        self.prompt_taken = True
        return CYCLE_PROMPT


def user_prompts(messages: Sequence[ModelMessage]) -> list[str]:
    return [
        cast(str, part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]


async def run_first_agent_recorded(
    *, scenario: SmokeScenario, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[CyclePromptSent], FlakyModelRecorder]:
    """Run the smoke scenario, recording the first agent's requests."""
    recorders: list[FlakyModelRecorder] = []

    def build_recorded(
        *, turns: Sequence[ScriptedTurn], when_exhausted: Sequence[ScriptedTurn] | None
    ) -> FunctionModel:
        scripted = BUILD_SCRIPTED_MODEL(turns=turns, when_exhausted=when_exhausted)
        if turns and turns[0] == RECORD_TURN:
            recorder = FlakyModelRecorder(scripted=scripted, failing=frozenset())
            recorders.append(recorder)
            return recorder.model()
        return scripted

    monkeypatch.setattr(simulation_harness, "build_scripted_model", build_recorded)
    result = await run_simulation(
        scenario=scenario,
        scripts={
            FIRST_AGENT_ID: [RECORD_TURN, SayTurn(text="done")],
            SECOND_AGENT_ID: [SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    [recorder] = recorders
    return result.of_type(event_type=CyclePromptSent), recorder


def smoke_knobs() -> SmokeKnobs:
    return SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})


async def test_a_prompt_before_the_first_request_opens_the_next_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent, recorder = await run_first_agent_recorded(
        scenario=PromptingSmokeScenario(knobs=smoke_knobs()),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert [event.prompt for event in sent] == [CYCLE_PROMPT]
    assert [event.agent_id for event in sent] == [FIRST_AGENT_ID]
    assert user_prompts(messages=recorder.requests[0]) == [INITIAL_PROMPT, CYCLE_PROMPT]


async def test_a_scenario_that_returns_no_prompt_leaves_the_cycle_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent, recorder = await run_first_agent_recorded(
        scenario=SmokeScenario(knobs=smoke_knobs()),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert sent == []
    assert user_prompts(messages=recorder.requests[0]) == [INITIAL_PROMPT]
