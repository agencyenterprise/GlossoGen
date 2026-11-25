"""The run records each agent's tools in the order its model receives them."""

from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from glossogen.models.communication_tool_names import LIST_CHANNELS_TOOL_NAME
from glossogen.models.event import AgentRegistered
from glossogen.testing import simulation_harness
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, observe_requests
from glossogen.testing.simulation_harness import never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)


class HidingSmokeScenario(SmokeScenario):
    """The smoke scenario with ``list_channels`` hidden from the second agent."""

    def hidden_base_tools(self, agent_id: str) -> frozenset[str]:
        if agent_id == SECOND_AGENT_ID:
            return frozenset({LIST_CHANNELS_TOOL_NAME})
        return frozenset()


class ToolOrderRecorder:
    """Records the tool names of the first request each scripted model receives."""

    def __init__(self) -> None:
        self.first_request_tools: list[list[str]] = []

    def wrap(self, scripted: FunctionModel) -> FunctionModel:
        seen: list[str] = []
        self.first_request_tools.append(seen)

        def record(messages: list[ModelMessage], info: AgentInfo) -> None:
            _ = messages
            if not seen:
                seen.extend(tool.name for tool in info.function_tools)

        return observe_requests(model=scripted, observer=record)


async def test_each_registration_lists_the_tools_in_the_order_the_model_receives_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = ToolOrderRecorder()
    original_builder = simulation_harness.build_scripted_model

    def build(
        *, turns: Sequence[ScriptedTurn], when_exhausted: Sequence[ScriptedTurn] | None
    ) -> FunctionModel:
        return recorder.wrap(scripted=original_builder(turns=turns, when_exhausted=when_exhausted))

    monkeypatch.setattr(simulation_harness, "build_scripted_model", build)
    result = await run_simulation(
        scenario=HidingSmokeScenario(
            knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
        ),
        scripts={FIRST_AGENT_ID: [SayTurn(text="done")], SECOND_AGENT_ID: [SayTurn(text="done")]},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    registrations = result.of_type(event_type=AgentRegistered)
    registered = {tuple(registration.tool_names) for registration in registrations}
    received = {tuple(names) for names in recorder.first_request_tools}
    # The two agents are offered different tools, so each list received can only
    # match its own agent's registration.
    assert len(registered) == 2
    assert received == registered
    # The order the model receives is not alphabetical.
    assert all(list(names) != sorted(names) for names in registered)
    for registration in registrations:
        assert [d.name for d in registration.tool_definitions] == registration.tool_names
