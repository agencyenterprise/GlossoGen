"""``read_notifications`` parks an agent in the runner and resumes it on its wait condition.

Runs the real runner, MCP server, wait registry and game clock against scripted
agents, so the assertions are about what the event log records.
"""

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import (
    AgentInfo,
    BuiltinToolCallsReturns,
    DeltaThinkingCalls,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)

from glossogen.testing import simulation_harness
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    RECORD_TOOL_NAME,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

READ = "read_notifications"


class WaitingSmokeScenario(SmokeScenario):
    """The smoke scenario, ending a round as soon as every agent is parked for good."""

    def ends_round_when_all_agents_waiting(self) -> bool:
        return True


def smoke(round_count: int) -> SmokeScenario:
    return SmokeScenario(
        knobs=SmokeKnobs(round_count=round_count, max_round_duration_seconds=45, model_overrides={})
    )


def waiting_smoke(round_count: int) -> WaitingSmokeScenario:
    return WaitingSmokeScenario(
        knobs=SmokeKnobs(round_count=round_count, max_round_duration_seconds=45, model_overrides={})
    )


BRIEFING = ToolTurn(tool_name=READ, args={})
"""The round's briefing is queued before an agent's first call; this takes it."""


def wait_turn(wait_for: str) -> ToolTurn:
    return ToolTurn(tool_name=READ, args={"wait_for": wait_for})


def send_turn(text: str) -> ToolTurn:
    return ToolTurn(
        tool_name="send_message",
        args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
    )


def first_wait(result: SimulationResult, agent_id: str, wait_for: str) -> dict[str, Any]:
    """The agent's first ``wait_registered`` event of that kind."""
    return next(
        e
        for e in result.of_type(event_type="wait_registered")
        if e["agent_id"] == agent_id and e["wait_for"] == wait_for
    )


def resume_of(result: SimulationResult, wait: dict[str, Any]) -> dict[str, Any]:
    """The ``agent_resumed`` event that ended ``wait``."""
    return next(
        e for e in result.of_type(event_type="agent_resumed") if e["wait_id"] == wait["wait_id"]
    )


def read_results_of(result: SimulationResult, agent_id: str) -> list[str]:
    return [
        e["result"]
        for e in result.of_type(event_type="tool_result_received")
        if e["agent_id"] == agent_id and e["tool_name"] == READ
    ]


def round_end_triggers(result: SimulationResult) -> list[str]:
    return [e["trigger"] for e in result.of_type(event_type="round_ended")]


async def run(
    scenario: SmokeScenario,
    first: Sequence[ScriptedTurn],
    second: Sequence[ScriptedTurn],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    return await run_simulation(
        scenario=scenario,
        scripts={FIRST_AGENT_ID: list(first), SECOND_AGENT_ID: list(second)},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


async def test_a_message_wait_resumes_on_a_teammates_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run(
        scenario=smoke(round_count=1),
        first=[BRIEFING, wait_turn(wait_for="message"), SayTurn(text="got it")],
        second=[BRIEFING, send_turn(text="column one is mine"), SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    wait = first_wait(result=result, agent_id=FIRST_AGENT_ID, wait_for="message")
    assert wait["deadline_s"] is None
    assert resume_of(result=result, wait=wait)["wake_reasons"] == ["new_message"]
    assert '"type": "new_messages"' in read_results_of(result=result, agent_id=FIRST_AGENT_ID)[1]


async def test_a_message_wait_is_not_resumed_by_the_agents_own_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run(
        scenario=smoke(round_count=1),
        first=[
            BRIEFING,
            send_turn(text="mine"),
            wait_turn(wait_for="message"),
            SayTurn(text="done"),
        ],
        second=[BRIEFING, SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    resume = resume_of(
        result=result, wait=first_wait(result=result, agent_id=FIRST_AGENT_ID, wait_for="message")
    )
    assert resume["wake_reasons"] == ["done"]
    assert resume["terminated"] is True
    assert '"type": "done"' in read_results_of(result=result, agent_id=FIRST_AGENT_ID)[1]


async def test_a_next_round_wait_sleeps_through_messages_until_the_next_briefing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run(
        scenario=smoke(round_count=2),
        first=[BRIEFING, wait_turn(wait_for="next_round"), SayTurn(text="round two")],
        second=[BRIEFING, send_turn(text="are you there"), SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    resume = resume_of(
        result=result,
        wait=first_wait(result=result, agent_id=FIRST_AGENT_ID, wait_for="next_round"),
    )
    assert resume["wake_reasons"] == ["next_round"]
    assert resume["round_number"] == 2


async def test_invalid_arguments_are_answered_without_parking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run(
        scenario=smoke(round_count=1),
        first=[ToolTurn(tool_name=READ, args={"wait_for": "forever"}), SayTurn(text="oops")],
        second=[SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    first_result = read_results_of(result=result, agent_id=FIRST_AGENT_ID)[0]
    assert first_result.startswith("Invalid arguments for read_notifications")
    first_waits = [
        e for e in result.of_type(event_type="wait_registered") if e["agent_id"] == FIRST_AGENT_ID
    ]
    assert all(e["wait_for"] == "any" for e in first_waits)


def calling_two_tools_first() -> FunctionModel:
    """A model whose first response calls ``read_notifications`` alongside another tool."""
    responses = 0

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns]:
        nonlocal responses
        _ = messages, info
        responses += 1
        if responses == 1:
            yield {
                0: DeltaToolCall(name=READ, json_args="{}"),
                1: DeltaToolCall(
                    name=RECORD_TOOL_NAME, json_args=json.dumps({"finding": "sibling"})
                ),
            }
            return
        if responses % 2 == 0:
            yield "done"
            return
        yield {0: DeltaToolCall(name=READ, json_args="{}")}

    return FunctionModel(stream_function=stream)


async def test_a_call_alongside_other_tools_does_not_park_and_the_siblings_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_builder = simulation_harness.build_scripted_model

    def build(
        *, turns: Sequence[ScriptedTurn], when_exhausted: Sequence[ScriptedTurn] | None
    ) -> FunctionModel:
        if not turns:
            return calling_two_tools_first()
        return original_builder(turns=turns, when_exhausted=when_exhausted)

    monkeypatch.setattr(simulation_harness, "build_scripted_model", build)
    result = await run(
        scenario=smoke(round_count=1),
        first=[],
        second=[SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert (
        "cannot be issued in parallel" in read_results_of(result=result, agent_id=FIRST_AGENT_ID)[0]
    )
    recorded = [
        e for e in result.tool_calls(tool_name=RECORD_TOOL_NAME) if e["agent_id"] == FIRST_AGENT_ID
    ]
    assert len(recorded) == 1


async def test_a_round_ends_finished_once_every_agent_waits_for_the_next_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run(
        scenario=waiting_smoke(round_count=1),
        first=[BRIEFING, wait_turn(wait_for="next_round"), SayTurn(text="done")],
        second=[BRIEFING, wait_turn(wait_for="next_round"), SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert round_end_triggers(result=result) == ["all_agents_finished"]


async def test_a_round_ends_waiting_when_some_agent_waits_for_a_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run(
        scenario=waiting_smoke(round_count=1),
        first=[BRIEFING, wait_turn(wait_for="next_round"), SayTurn(text="done")],
        second=[BRIEFING, wait_turn(wait_for="message"), SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert round_end_triggers(result=result) == ["all_agents_waiting"]


async def test_a_wait_with_a_deadline_keeps_the_exact_rule_from_ending_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run(
        scenario=waiting_smoke(round_count=1),
        first=[BRIEFING, wait_turn(wait_for="next_round"), SayTurn(text="done")],
        second=[BRIEFING, wait_turn(wait_for="any"), SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert round_end_triggers(result=result) == ["all_agents_idle"]


async def test_a_scenario_that_does_not_opt_in_ends_its_rounds_on_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run(
        scenario=smoke(round_count=1),
        first=[BRIEFING, wait_turn(wait_for="next_round"), SayTurn(text="done")],
        second=[BRIEFING, wait_turn(wait_for="next_round"), SayTurn(text="done")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert round_end_triggers(result=result) == ["all_agents_idle"]
