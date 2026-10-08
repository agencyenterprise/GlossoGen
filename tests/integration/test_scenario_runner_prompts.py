"""A scenario can replace the runner prompts, and the run records what it used."""

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, SystemPromptPart, UserPromptPart
from pydantic_ai.models.function import (
    AgentInfo,
    BuiltinToolCallsReturns,
    DeltaThinkingCalls,
    DeltaToolCalls,
    FunctionModel,
)

from glossogen.evaluation.log_reader import load_events
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runners.communication_protocol import INITIAL_PROMPT, runner_prompts_from_events
from glossogen.testing import simulation_harness
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

CUSTOM = RunnerPrompts(
    system_suffix="Use the shared board.",
    initial="Read your card, then act.",
    continuation="Carry on from the board.",
)


class PromptingSmokeScenario(SmokeScenario):
    """The smoke scenario with its own runner prompts."""

    def runner_prompts(self, agent_id: str) -> RunnerPrompts | None:
        _ = agent_id
        return CUSTOM


class RequestRecorder:
    """Records the first request each agent's model receives."""

    def __init__(self) -> None:
        self.first_request: dict[str, list[ModelMessage]] = {}

    def wrap(self, agent_key: str, scripted: FunctionModel) -> FunctionModel:
        async def stream(
            messages: list[ModelMessage], info: AgentInfo
        ) -> AsyncIterator[str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns]:
            self.first_request.setdefault(agent_key, list(messages))
            assert scripted.stream_function is not None
            async for chunk in scripted.stream_function(messages, info):
                yield chunk

        return FunctionModel(stream_function=stream)


async def run_recorded(
    scenario: SmokeScenario, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SimulationResult, RequestRecorder]:
    recorder = RequestRecorder()
    original_builder = simulation_harness.build_scripted_model
    built = 0

    def build(
        *, turns: Sequence[ScriptedTurn], when_exhausted: Sequence[ScriptedTurn] | None
    ) -> FunctionModel:
        nonlocal built
        built += 1
        scripted = original_builder(turns=turns, when_exhausted=when_exhausted)
        return recorder.wrap(agent_key=f"agent-{built}", scripted=scripted)

    monkeypatch.setattr(simulation_harness, "build_scripted_model", build)
    result = await run_simulation(
        scenario=scenario,
        scripts={FIRST_AGENT_ID: [SayTurn(text="done")], SECOND_AGENT_ID: [SayTurn(text="done")]},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    return result, recorder


def parts_of(messages: list[ModelMessage]) -> tuple[str, str]:
    """The system prompt and the first user prompt of a request."""
    request = messages[0]
    assert isinstance(request, ModelRequest)
    system = next(p.content for p in request.parts if isinstance(p, SystemPromptPart))
    user = next(p.content for p in request.parts if isinstance(p, UserPromptPart))
    assert isinstance(user, str)
    return system, user


def knobs() -> SmokeKnobs:
    return SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})


async def test_agents_receive_the_scenarios_prompts_and_the_run_records_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, recorder = await run_recorded(
        scenario=PromptingSmokeScenario(knobs=knobs()), tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    for messages in recorder.first_request.values():
        system, user = parts_of(messages=messages)
        assert system.endswith("\n\nUse the shared board.")
        assert user == "Read your card, then act."
    registrations = result.of_type(event_type="agent_registered")
    assert all(r["runner_prompts"] == CUSTOM.model_dump() for r in registrations)
    events = await load_events(log_path=result.log_path)
    assert (
        runner_prompts_from_events(events=events, agent_id=FIRST_AGENT_ID, role_name="unused")
        == CUSTOM
    )


async def test_a_scenario_on_the_platform_prompts_records_nothing_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, recorder = await run_recorded(
        scenario=SmokeScenario(knobs=knobs()), tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    for messages in recorder.first_request.values():
        assert parts_of(messages=messages)[1] == INITIAL_PROMPT
    assert all("runner_prompts" not in r for r in result.of_type(event_type="agent_registered"))
