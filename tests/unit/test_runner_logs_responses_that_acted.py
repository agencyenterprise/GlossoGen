"""A model response whose tool calls started to run is logged, however its cycle ends.

A cycle can stop while a tool call runs: the run's drain cancels a runner that
does not exit, a swap cancels the old runner, or an attempt fails. The response
that made the call is still pending then, because a response is logged when the
next one starts or when its cycle ends.
"""

import asyncio
from pathlib import Path

import pytest
from pydantic_ai.messages import ThinkingPart

from glossogen.models.event import LLMResponseReceived, ToolCallInvoked
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.runners.pydantic_ai_runner import (
    _StreamingState,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.runners.token_id_log import TokenIdLog
from glossogen.runtime.autonomous_supervisor import AutonomousSupervisor
from glossogen.scenario_contract.scenario_tool import ScenarioTool
from glossogen.testing.scripted_agent import SayTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    RECORD_TOOL_NAME,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)


def unlogged_call_ids(result: SimulationResult) -> list[str]:
    """The ids of invoked tool calls that no logged response holds."""
    logged = {
        call.call_id
        for response in result.of_type(event_type=LLMResponseReceived)
        for call in response.tool_calls
    }
    return [
        invoked.call_id
        for invoked in result.of_type(event_type=ToolCallInvoked)
        if invoked.call_id not in logged
    ]


def test_a_failed_attempt_keeps_a_response_whose_tool_calls_ran() -> None:
    state = _StreamingState(token_id_log=TokenIdLog())
    state.mark_attempt_start()
    state.start_thinking_part(part_index=0, part=ThinkingPart(content="record it"))
    call = ToolCallRequest(tool_name=RECORD_TOOL_NAME, arguments={"finding": "x"}, call_id="c1")
    state.accumulated_tool_calls.append(call)

    state.discard_failed_attempt()

    assert state.accumulated_tool_calls == [call]
    assert state.thinking_text() == "record it"


async def test_a_runner_cancelled_inside_a_tool_call_logs_the_response_that_made_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first agent's tool never returns, so the drain at the end of the run cancels it."""
    entered = asyncio.Event()

    async def record_never_returns(agent_id: str, finding: str) -> str:
        """Hold the calling agent inside its tool call until it is cancelled."""
        _ = agent_id
        _ = finding
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("the held tool call returned")

    def held_record_tool(self: SmokeScenario) -> list[ScenarioTool]:
        _ = self
        return [
            ScenarioTool(
                name=RECORD_TOOL_NAME,
                description="Record a finding for this round.",
                executor=record_never_returns,
            )
        ]

    def drain_without_waiting(self: AutonomousSupervisor) -> float:
        """Cancel every runner still running once the run is done: the held one never exits."""
        _ = self
        return 0.0

    def timed_out_once_held(phase_age: float, limit: float) -> bool:
        """End each phase once the first agent is inside its tool call, and not before."""
        _ = phase_age
        _ = limit
        return entered.is_set()

    monkeypatch.setattr(SmokeScenario, "get_tools", held_record_tool)
    monkeypatch.setattr(AutonomousSupervisor, "_runner_drain_seconds", drain_without_waiting)
    result = await run_simulation(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
        ),
        scripts={
            FIRST_AGENT_ID: [ToolTurn(tool_name=RECORD_TOOL_NAME, args={"finding": "held"})],
            SECOND_AGENT_ID: [SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=timed_out_once_held,
    )

    [held] = result.tool_calls(tool_name=RECORD_TOOL_NAME)
    assert unlogged_call_ids(result=result) == []
    [response] = [
        response
        for response in result.of_type(event_type=LLMResponseReceived)
        if held.call_id in {call.call_id for call in response.tool_calls}
    ]
    assert response.stop_reason == "tool_use"
    assert response.usage.input_tokens > 0
