"""A scenario's closing prompt: one more message each agent gets once the run has completed.

The runner sends ``RunnerPrompts.closing`` after the agent's last turn, in the
agent's own conversation, with no tool call allowed, and logs the exchange as
``ClosingPromptAnswered``, or ``ClosingPromptFailed``, before ``SimulationEnded``.

The tests check that the prompt follows the agent's own history with
``tool_choice`` none, that the answer is not logged as an
``LLMResponseReceived``, that an agent swapped out mid-run is not asked, and that
a failed exchange is logged and still leaves ``simulation_ended``.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai.models.function import (
    AgentInfo,
    BuiltinToolCallsReturns,
    DeltaThinkingCalls,
    DeltaToolCalls,
    FunctionModel,
)
from pydantic_ai.usage import RunUsage

from glossogen.model_catalog import Provider
from glossogen.models.event import (
    AgentResumed,
    AgentSwappedMidRun,
    ClosingPromptAnswered,
    ClosingPromptFailed,
    LLMResponseReceived,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
)
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runners.communication_protocol import CONTINUE_PROMPT, INITIAL_PROMPT
from glossogen.runtime.scheduled_events import ScheduledEvent, SwapAgent
from glossogen.testing import simulation_harness
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

CLOSING = "The run is over. Describe the protocol you used, if there was one."

# The harness routes each agent to its script by model name, so the swapped-in
# agent needs a name of its own to get a script of its own.
REPLACEMENT_SCRIPT_KEY = "first_agent_gen2"
REPLACEMENT_MODEL = f"scripted::{REPLACEMENT_SCRIPT_KEY}"


class ClosingSmokeScenario(SmokeScenario):
    """The smoke scenario on the platform's prompts, plus a closing prompt."""

    def runner_prompts(self, agent_id: str) -> RunnerPrompts | None:
        _ = agent_id
        return RunnerPrompts(
            system_suffix="Use the link channel.",
            initial=INITIAL_PROMPT,
            continuation=CONTINUE_PROMPT,
            closing=CLOSING,
        )


class ProviderUnavailable(RuntimeError):
    """What the closing exchange raises when the provider is down."""


class PlainRequestRecorder:
    """Records every plain request each agent's model receives.

    The runner streams its game cycles, so the plain path carries the closing
    prompt alone.
    """

    def __init__(self) -> None:
        self.requests: dict[str, list[tuple[list[ModelMessage], AgentInfo]]] = {}

    def wrap(self, agent_key: str, scripted: FunctionModel) -> FunctionModel:
        plain = scripted.function
        streamed = scripted.stream_function
        assert plain is not None
        assert streamed is not None

        async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            self.requests.setdefault(agent_key, []).append((list(messages), info))
            played = plain(messages, info)
            if isinstance(played, ModelResponse):
                return played
            return await played

        async def stream(
            messages: list[ModelMessage], info: AgentInfo
        ) -> AsyncIterator[str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns]:
            async for chunk in streamed(messages, info):
                yield chunk

        return FunctionModel(respond, stream_function=stream)


def play_then_answer(*, answer: str) -> list[ScriptedTurn]:
    """Read the briefing, park until the run ends, end the turn, then answer the closing prompt."""
    return [
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="briefed"),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="the run is over"),
        SayTurn(text=answer),
    ]


async def run_smoke(
    *,
    scenario: SmokeScenario,
    scripts: dict[str, Sequence[ScriptedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SimulationResult, PlainRequestRecorder]:
    recorder = PlainRequestRecorder()
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
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    return result, recorder


def build_scenario(
    *, round_count: int, scheduled_events: list[ScheduledEvent]
) -> ClosingSmokeScenario:
    return ClosingSmokeScenario(
        knobs=SmokeKnobs(
            round_count=round_count,
            max_round_duration_seconds=45,
            model_overrides={},
            scheduled_events=scheduled_events,
        )
    )


def index_of(*, events: list[SimulationEvent], event: SimulationEvent) -> int:
    """Position of ``event`` in the log, found by its id."""
    return next(index for index, logged in enumerate(events) if logged.event_id == event.event_id)


async def test_each_agent_answers_the_closing_prompt_in_its_own_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prompt follows the whole game, no tool call is allowed, and the answer is logged."""
    result, recorder = await run_smoke(
        scenario=build_scenario(round_count=1, scheduled_events=[]),
        scripts={
            FIRST_AGENT_ID: play_then_answer(answer="first: one word per round"),
            SECOND_AGENT_ID: play_then_answer(answer="second: no protocol"),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    answers = {event.agent_id: event for event in result.of_type(event_type=ClosingPromptAnswered)}
    assert answers[FIRST_AGENT_ID].answer == "first: one word per round"
    assert answers[SECOND_AGENT_ID].answer == "second: no protocol"
    assert all(answer.prompt == CLOSING for answer in answers.values())

    end_index = result.first_index(event_type=SimulationEnded, round_number=None)
    for answer in answers.values():
        done_wake = next(
            index
            for index, event in enumerate(result.events)
            if isinstance(event, AgentResumed)
            and event.agent_id == answer.agent_id
            and event.terminated
        )
        assert done_wake < index_of(events=result.events, event=answer) < end_index

    for requests in recorder.requests.values():
        [(messages, info)] = requests
        assert info.model_settings is not None
        assert info.model_settings.get("tool_choice") == "none"
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        assert [part.content for part in last.parts if isinstance(part, UserPromptPart)] == [
            CLOSING
        ]
        # The game came before it: the agent answers from the conversation it played in.
        assert any(isinstance(message, ModelResponse) for message in messages[:-1])


async def test_the_answer_is_not_logged_as_play(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transcripts are read from ``LLMResponseReceived``; an answer there would be a game turn."""
    result, _ = await run_smoke(
        scenario=build_scenario(round_count=1, scheduled_events=[]),
        scripts={
            FIRST_AGENT_ID: play_then_answer(answer="first: one word per round"),
            SECOND_AGENT_ID: play_then_answer(answer="second: no protocol"),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert result.of_type(event_type=ClosingPromptAnswered), "no agent answered"

    texts = [event.text for event in result.of_type(event_type=LLMResponseReceived)]
    assert all(
        "one word per round" not in text and "no protocol" not in text
        for text in texts
        if text is not None
    )


async def test_without_a_closing_prompt_nothing_is_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, recorder = await run_smoke(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
        ),
        scripts={
            FIRST_AGENT_ID: play_then_answer(answer="never asked"),
            SECOND_AGENT_ID: play_then_answer(answer="never asked"),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert result.of_type(event_type=ClosingPromptAnswered) == []
    assert recorder.requests == {}


async def test_only_the_agent_holding_the_seat_at_the_end_is_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A swapped-out agent is woken with done too, but the run had not ended for it."""
    result, _ = await run_smoke(
        scenario=build_scenario(
            round_count=2,
            scheduled_events=[
                SwapAgent(
                    at_round=2,
                    agent_id=FIRST_AGENT_ID,
                    model=REPLACEMENT_MODEL,
                    provider=Provider.ANTHROPIC,
                )
            ],
        ),
        scripts={
            FIRST_AGENT_ID: play_then_answer(answer="predecessor"),
            REPLACEMENT_SCRIPT_KEY: play_then_answer(answer="successor"),
            SECOND_AGENT_ID: play_then_answer(answer="second"),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    seat_answers = [
        event
        for event in result.of_type(event_type=ClosingPromptAnswered)
        if event.agent_id == FIRST_AGENT_ID
    ]
    assert [answer.answer for answer in seat_answers] == ["successor"]
    assert seat_answers[0].model == REPLACEMENT_MODEL
    swap_index = result.first_index(event_type=AgentSwappedMidRun, round_number=None)
    assert index_of(events=result.events, event=seat_answers[0]) > swap_index


async def test_a_failed_exchange_is_logged_and_the_run_still_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log says why an agent has no answer, and the run keeps its end marker."""

    async def provider_down(*, agent: object, history: object, prompt: str, usage: RunUsage) -> str:
        _ = agent, history, prompt, usage
        raise ProviderUnavailable("provider unavailable")

    monkeypatch.setattr("glossogen.runners.pydantic_ai_runner.answer_closing_prompt", provider_down)
    result, _ = await run_smoke(
        scenario=build_scenario(round_count=1, scheduled_events=[]),
        scripts={
            FIRST_AGENT_ID: play_then_answer(answer="never logged"),
            SECOND_AGENT_ID: play_then_answer(answer="never logged"),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert result.of_type(event_type=ClosingPromptAnswered) == []
    failures = result.of_type(event_type=ClosingPromptFailed)
    assert sorted(failure.agent_id for failure in failures) == [FIRST_AGENT_ID, SECOND_AGENT_ID]
    assert all(failure.error_type == "ProviderUnavailable" for failure in failures)
    assert all(failure.prompt == CLOSING for failure in failures)
    end_index = result.first_index(event_type=SimulationEnded, round_number=None)
    assert all(index_of(events=result.events, event=failure) < end_index for failure in failures)
    [ended] = result.of_type(event_type=SimulationEnded)
    assert ended.reason == RunStatus.SCENARIO_COMPLETE


async def test_a_cancelled_exchange_is_logged_before_the_cancellation_carries_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shutdown deadline can cancel an exchange before its own limit runs out.

    The stub raises what the supervisor's cancel delivers, so no deadline has to
    pass for real.
    """

    async def cancelled(*, agent: object, history: object, prompt: str, usage: RunUsage) -> str:
        _ = agent, history, prompt, usage
        raise asyncio.CancelledError

    monkeypatch.setattr("glossogen.runners.pydantic_ai_runner.answer_closing_prompt", cancelled)
    result, _ = await run_smoke(
        scenario=build_scenario(round_count=1, scheduled_events=[]),
        scripts={
            FIRST_AGENT_ID: play_then_answer(answer="never logged"),
            SECOND_AGENT_ID: play_then_answer(answer="never logged"),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    failures = result.of_type(event_type=ClosingPromptFailed)
    assert sorted(failure.agent_id for failure in failures) == [FIRST_AGENT_ID, SECOND_AGENT_ID]
    assert all(failure.error_type == "CancelledError" for failure in failures)
    assert all(failure.message == "" for failure in failures)
    [ended] = result.of_type(event_type=SimulationEnded)
    assert ended.reason == RunStatus.SCENARIO_COMPLETE
