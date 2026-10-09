"""An agent is offered its own tools, and a tool's refusal reaches it in the tool's words.

The runner builds each agent's tools in-process, so what an agent can call is
decided when its tools are built, and a tool that refuses a call raises
``ValueError`` and the agent reads that sentence as the tool's error.
"""

from pathlib import Path

import pytest

from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import AgentRegistered, ToolResultReceived
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.testing.scripted_agent import SayTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    RECORD_TOOL_NAME,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

STABILIZE = "stabilize"
CRASH = "crash"
REFUSAL = "Only the first agent can stabilize."


class RefusingSmokeScenario(SmokeScenario):
    """Adds a tool only the first agent may call, and one that crashes."""

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        agents = super().get_agents(default_model=default_model, default_provider=default_provider)
        for agent in agents:
            if agent.agent_id == FIRST_AGENT_ID:
                agent.tool_names = [*agent.tool_names, STABILIZE, CRASH]
        return agents

    def get_tools(self) -> list[ScenarioTool]:
        async def stabilize(agent_id: str, action: str) -> str:
            if agent_id != FIRST_AGENT_ID:
                raise ValueError(REFUSAL)
            return f"stabilized with {action}"

        async def crash(agent_id: str) -> str:
            _ = agent_id
            raise KeyError("internal detail")

        return [
            *super().get_tools(),
            ScenarioTool(name=STABILIZE, description="Stabilize.", executor=stabilize),
            ScenarioTool(name=CRASH, description="Crash.", executor=crash),
        ]


async def run_refusing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimulationResult:
    return await run_simulation(
        scenario=RefusingSmokeScenario(
            knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
        ),
        scripts={
            FIRST_AGENT_ID: [
                ToolTurn(tool_name=STABILIZE, args={"action": "gentle"}),
                ToolTurn(tool_name=CRASH, args={}),
                SayTurn(text="done"),
            ],
            SECOND_AGENT_ID: [
                ToolTurn(tool_name=STABILIZE, args={"action": "rough"}),
                SayTurn(text="done"),
            ],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def results_of(result: SimulationResult, agent_id: str, tool_name: str) -> list[str]:
    return [
        e.result
        for e in result.of_type(event_type=ToolResultReceived)
        if e.agent_id == agent_id and e.tool_name == tool_name
    ]


def offered_to(result: SimulationResult, agent_id: str) -> list[str]:
    registration = next(
        e for e in result.of_type(event_type=AgentRegistered) if e.agent_id == agent_id
    )
    return [definition.name for definition in registration.tool_definitions]


async def test_an_agent_is_offered_only_the_scenario_tools_its_role_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_refusing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    first = offered_to(result=result, agent_id=FIRST_AGENT_ID)
    second = offered_to(result=result, agent_id=SECOND_AGENT_ID)
    assert {STABILIZE, CRASH, RECORD_TOOL_NAME, "send_message", "read_notifications"} <= set(first)
    assert STABILIZE not in second and CRASH not in second
    assert "read_notifications" in second


async def test_a_tool_the_agent_was_not_offered_is_unknown_to_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_refusing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    answers = results_of(result=result, agent_id=SECOND_AGENT_ID, tool_name=STABILIZE)
    assert len(answers) == 1
    assert answers[0].startswith("Unknown tool name: 'stabilize'")
    assert "rough" not in answers[0]


async def test_an_allowed_call_runs_and_the_schema_hides_agent_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_refusing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert results_of(result=result, agent_id=FIRST_AGENT_ID, tool_name=STABILIZE) == [
        "stabilized with gentle"
    ]
    registration = next(
        e for e in result.of_type(event_type=AgentRegistered) if e.agent_id == FIRST_AGENT_ID
    )
    stabilize = next(d for d in registration.tool_definitions if d.name == STABILIZE)
    assert sorted(stabilize.input_schema["properties"]) == ["action"]


async def test_a_crash_reaches_the_agent_as_a_generic_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_refusing(tmp_path=tmp_path, monkeypatch=monkeypatch)
    crash_results = results_of(result=result, agent_id=FIRST_AGENT_ID, tool_name=CRASH)
    assert len(crash_results) == 1
    assert f"Error executing tool {CRASH}" in crash_results[0]
    assert "internal detail" not in crash_results[0]
