"""A retried model request resumes at the request that failed.

A cycle can run several tool calls before its last model request. If that
request fails and the retry restarted the cycle from its first prompt, the model
would be asked again from a history without those calls, and could repeat them.
A request that fails every retry is not re-sent: the next cycle restarts from the
last completed one.
"""

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import (
    AgentInfo,
    BuiltinToolCallsReturns,
    DeltaThinkingCalls,
    DeltaToolCalls,
    FunctionModel,
)

from glossogen.models.event import AgentRunCycleFailed, LLMResponseReceived
from glossogen.models.event_base import TokenUsage
from glossogen.runners import pydantic_ai_runner
from glossogen.testing import simulation_harness
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    RECORD_TOOL_NAME,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

FAILING_REQUEST_NUMBER = 2
EXHAUSTED_REQUEST_NUMBERS = frozenset({2, 3, 4})
RECORD_TURN = ToolTurn(tool_name=RECORD_TOOL_NAME, args={"finding": "retry probe"})
# Captured at import, so a test that runs the harness twice wraps the harness's own
# builder both times rather than wrapping its first wrapper.
BUILD_SCRIPTED_MODEL = simulation_harness.build_scripted_model


async def no_retry_pause(_seconds: float) -> None:
    """Stand in for tenacity's sleep: the retry pause is wall-clock time a test does not spend."""
    return None


class ProviderUnavailable(RuntimeError):
    """The error the flaky model raises once."""


class FlakyModelRecorder:
    """Wraps a scripted model so the requests numbered in ``failing`` fail, and records all."""

    def __init__(self, scripted: FunctionModel, failing: frozenset[int]) -> None:
        self._scripted = scripted
        self._failing = failing
        self.requests: list[list[ModelMessage]] = []

    def model(self) -> FunctionModel:
        """Return the wrapping model."""

        async def stream(
            messages: list[ModelMessage], info: AgentInfo
        ) -> AsyncIterator[str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns]:
            self.requests.append(list(messages))
            if len(self.requests) in self._failing:
                raise ProviderUnavailable("provider unavailable")
            assert self._scripted.stream_function is not None
            async for chunk in self._scripted.stream_function(messages, info):
                yield chunk

        return FunctionModel(stream_function=stream)


def tool_returns_named(messages: Sequence[ModelMessage], tool_name: str) -> list[ToolReturnPart]:
    """Every tool return for ``tool_name`` in ``messages``."""
    return [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == tool_name
    ]


async def run_first_agent_failing(
    failing: frozenset[int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SimulationResult, FlakyModelRecorder]:
    """Run the smoke scenario with the first agent's requests in ``failing`` raising."""
    recorders: dict[str, FlakyModelRecorder] = {}

    def build_flaky_for_first_agent(
        *, turns: Sequence[ScriptedTurn], when_exhausted: Sequence[ScriptedTurn] | None
    ) -> FunctionModel:
        scripted = BUILD_SCRIPTED_MODEL(turns=turns, when_exhausted=when_exhausted)
        if turns and turns[0] == RECORD_TURN:
            recorder = FlakyModelRecorder(scripted=scripted, failing=failing)
            recorders[FIRST_AGENT_ID] = recorder
            return recorder.model()
        return scripted

    monkeypatch.setattr(simulation_harness, "build_scripted_model", build_flaky_for_first_agent)
    run_agent_call = pydantic_ai_runner._run_agent_call  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(cast(Any, run_agent_call).retry, "sleep", no_retry_pause)
    result = await run_simulation(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
        ),
        scripts={
            FIRST_AGENT_ID: [RECORD_TURN, SayTurn(text="done")],
            SECOND_AGENT_ID: [SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    return result, recorders[FIRST_AGENT_ID]


async def test_a_retry_resumes_at_the_failed_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, recorder = await run_first_agent_failing(
        failing=frozenset({FAILING_REQUEST_NUMBER}), tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    requests = recorder.requests
    failed = requests[FAILING_REQUEST_NUMBER - 1]
    retried = requests[FAILING_REQUEST_NUMBER]
    failed_returns = tool_returns_named(messages=failed, tool_name=RECORD_TOOL_NAME)
    retried_returns = tool_returns_named(messages=retried, tool_name=RECORD_TOOL_NAME)
    assert len(failed_returns) == 1
    assert [part.tool_call_id for part in retried_returns] == [
        part.tool_call_id for part in failed_returns
    ]
    assert len(retried) == len(failed)
    recorded = [
        call
        for call in result.tool_calls(tool_name=RECORD_TOOL_NAME)
        if call.agent_id == FIRST_AGENT_ID
    ]
    assert len(recorded) == 1
    assert result.of_type(event_type=AgentRunCycleFailed) == []


def first_cycle_usage(result: SimulationResult) -> TokenUsage:
    """The usage the first agent's first completed cycle reported."""
    return next(
        TokenUsage.model_validate(e.usage)
        for e in result.of_type(event_type=LLMResponseReceived)
        if e.agent_id == FIRST_AGENT_ID and e.stop_reason == "end_turn"
    )


async def test_a_retried_cycle_counts_every_attempts_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean, _ = await run_first_agent_failing(
        failing=frozenset(), tmp_path=tmp_path / "clean", monkeypatch=monkeypatch
    )
    retried, _ = await run_first_agent_failing(
        failing=frozenset({FAILING_REQUEST_NUMBER}),
        tmp_path=tmp_path / "retried",
        monkeypatch=monkeypatch,
    )
    assert first_cycle_usage(result=retried) == first_cycle_usage(result=clean)


async def test_a_request_that_fails_every_retry_is_not_sent_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, recorder = await run_first_agent_failing(
        failing=EXHAUSTED_REQUEST_NUMBERS, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    assert len(result.of_type(event_type=AgentRunCycleFailed)) == 1
    restarted = recorder.requests[max(EXHAUSTED_REQUEST_NUMBERS)]
    assert tool_returns_named(messages=restarted, tool_name=RECORD_TOOL_NAME) == []
