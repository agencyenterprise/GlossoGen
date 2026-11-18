"""Under ``briefing_as_user_message`` each round's briefing opens a new cycle as a user message.

The briefing leaves the ``read_notifications`` result, the runner ends the
player's cycle before its next model request, and the next cycle sends the
pending tool result followed by the briefing. The run logs ``CyclePromptSent``,
the rebuilt history puts the briefing where the player saw it, and a cycle that
fails every retry restarts with its briefing.
"""

import asyncio
import json
import shutil
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import (
    AgentInfo,
    BuiltinToolCallsReturns,
    DeltaThinkingCalls,
    DeltaToolCalls,
    FunctionModel,
)

from glossogen.atif_export.atif_models import AtifStepSource
from glossogen.atif_export.atif_trajectory_builder import build_agent_trajectories_from_run_dir
from glossogen.models.event import (
    AgentRunCycleFailed,
    CyclePromptSent,
    InjectionDelivered,
    LLMResponseReceived,
    StopReason,
    ToolResultReceived,
)
from glossogen.models.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME
from glossogen.run_replay.message_history_builder import (
    build_message_history,
    resolve_history_timestamp,
)
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.runners import pydantic_ai_runner
from glossogen.scenario_contract.platform_runner_prompts import runner_prompts_from_events
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.testing import simulation_harness
from glossogen.testing.scenario_runtime import assert_no_agent_crashed
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from tests.scenarios.signal_game.signal_game_play import (
    build,
    end_round,
    play,
    read,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("signal_game")

TWO_ROUNDS_AS_MESSAGES: dict[str, Any] = {"round_count": 2, "briefing_as_user_message": True}
LAST_WORDS = {PLAYER_A: "a: game over", PLAYER_B: "b: game over"}
# Captured at import, so each test wraps the harness's own builder.
BUILD_SCRIPTED_MODEL = simulation_harness.build_scripted_model


async def no_retry_pause(_seconds: float) -> None:
    """Stand in for tenacity's sleep: the retry pause is wall-clock time a test does not spend."""
    return None


class ProviderUnavailable(RuntimeError):
    """The error a failing request raises."""


class RequestRecorder:
    """Records every request a player's model receives; the numbered ones in ``failing`` raise."""

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


def two_rounds_then(*, last_words: str) -> list[ScriptedTurn]:
    """Finish each round on the start square, then end the turn the done wake leaves open."""
    return [
        read(),
        end_round(),
        wait_for_next_round(),
        end_round(),
        wait_for_next_round(),
        SayTurn(text=last_words),
    ]


async def play_two_rounds(
    *,
    failing: dict[str, frozenset[int]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SimulationResult, dict[str, RequestRecorder]]:
    """Play two rounds with briefings as messages, recording each player's requests.

    A run whose requests all succeed must have no failed cycle.
    """
    recorders: dict[str, RequestRecorder] = {}

    def build_recorded(
        *, turns: Sequence[ScriptedTurn], when_exhausted: Sequence[ScriptedTurn] | None
    ) -> FunctionModel:
        last = turns[-1]
        assert isinstance(last, SayTurn)
        agent_id = next(agent for agent, words in LAST_WORDS.items() if words == last.text)
        recorder = RequestRecorder(
            scripted=BUILD_SCRIPTED_MODEL(turns=turns, when_exhausted=when_exhausted),
            failing=failing[agent_id],
        )
        recorders[agent_id] = recorder
        return recorder.model()

    monkeypatch.setattr(simulation_harness, "build_scripted_model", build_recorded)
    run_agent_call = pydantic_ai_runner._run_agent_call  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(cast(Any, run_agent_call).retry, "sleep", no_retry_pause)
    async with asyncio.timeout(60):
        result = await run_simulation(
            scenario=build(preset_name="knobs_words", overrides=TWO_ROUNDS_AS_MESSAGES),
            scripts={
                agent_id: two_rounds_then(last_words=words)
                for agent_id, words in LAST_WORDS.items()
            },
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )
    if not any(failing.values()):
        assert_no_agent_crashed(result=result)
    return result, recorders


def briefings_for(result: SimulationResult, agent_id: str) -> list[str]:
    """The round briefings the game delivered to ``agent_id``, in round order."""
    return [
        event.text
        for event in result.of_type(event_type=InjectionDelivered)
        if event.agent_id == agent_id
    ]


def user_prompts(messages: Sequence[ModelMessage]) -> list[str]:
    """Every user prompt in ``messages``, in order."""
    return [
        cast(str, part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]


def shape(messages: Sequence[ModelMessage]) -> list[tuple[str, ...]]:
    """Each message as its parts' kinds, with prompt texts and tool names."""
    shaped: list[tuple[str, ...]] = []
    for message in messages:
        parts: list[str] = []
        for part in message.parts:
            if isinstance(part, SystemPromptPart):
                parts.append("system")
            elif isinstance(part, UserPromptPart):
                parts.append(f"user: {part.content}")
            elif isinstance(part, ToolReturnPart):
                parts.append(f"return: {part.tool_name}")
            elif isinstance(part, ToolCallPart):
                parts.append(f"call: {part.tool_name}")
        kind = "response"
        if isinstance(message, ModelRequest):
            kind = "request"
        shaped.append((kind, *parts))
    return shaped


async def test_each_briefing_opens_a_cycle_after_the_wait_that_brought_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, recorders = await play_two_rounds(
        failing={PLAYER_A: frozenset(), PLAYER_B: frozenset()},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    for agent_id, recorder in recorders.items():
        briefings = briefings_for(result=result, agent_id=agent_id)
        assert len(briefings) == 2
        last_request = recorder.requests[-1]
        assert user_prompts(messages=last_request)[1:] == briefings
        for position, message in enumerate(last_request):
            if position == 0 or not isinstance(message, ModelRequest):
                continue
            if isinstance(message.parts[0], UserPromptPart):
                before = last_request[position - 1]
                assert isinstance(before, ModelRequest)
                assert [cast(ToolReturnPart, part).tool_name for part in before.parts] == [
                    READ_NOTIFICATIONS_TOOL_NAME
                ]
        sent = [
            event.prompt
            for event in result.of_type(event_type=CyclePromptSent)
            if event.agent_id == agent_id
        ]
        assert sent == briefings


async def test_no_wait_result_carries_a_briefing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await play_two_rounds(
        failing={PLAYER_A: frozenset(), PLAYER_B: frozenset()},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    wakes = [
        json.loads(event.result)
        for event in result.of_type(event_type=ToolResultReceived)
        if event.tool_name == READ_NOTIFICATIONS_TOOL_NAME
    ]
    assert len(wakes) == 6
    assert all(wake["briefings"] == [] for wake in wakes)


async def test_the_response_before_each_briefing_is_logged_as_a_tool_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await play_two_rounds(
        failing={PLAYER_A: frozenset(), PLAYER_B: frozenset()},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    responses = [
        event
        for event in result.of_type(event_type=LLMResponseReceived)
        if event.agent_id == PLAYER_A
    ]
    assert [response.stop_reason for response in responses] == [
        StopReason.TOOL_USE,
        StopReason.TOOL_USE,
        StopReason.TOOL_USE,
        StopReason.TOOL_USE,
        StopReason.TOOL_USE,
        StopReason.END_TURN,
    ]


async def test_the_rebuilt_history_puts_each_briefing_where_the_player_saw_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, recorders = await play_two_rounds(
        failing={PLAYER_A: frozenset(), PLAYER_B: frozenset()},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    prompts = runner_prompts_from_events(
        events=result.events, agent_id=PLAYER_A, role_name=PLAYER_A
    )

    def rebuild(cutoff_round: int | None) -> list[ModelMessage]:
        return build_message_history(
            events=result.events,
            agent_id=PLAYER_A,
            system_prompt="system",
            runner_prompts=prompts,
            target_timestamp=resolve_history_timestamp(events=result.events),
            cutoff_round=cutoff_round,
            tool_calls_only=False,
            channel_visibility={},
            history_floor_round=None,
            filter_below_round=None,
            split_parallel_tool_calls=False,
        )

    live = recorders[PLAYER_A].requests[-1]
    rebuilt = rebuild(cutoff_round=None)
    assert shape(messages=rebuilt)[: len(live)] == shape(messages=live)
    assert isinstance(rebuilt[len(live)], ModelResponse)

    briefings = briefings_for(result=result, agent_id=PLAYER_A)
    assert user_prompts(messages=rebuild(cutoff_round=2))[1:] == briefings[:1]


async def test_the_atif_trajectory_has_each_briefing_as_a_user_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await play_two_rounds(
        failing={PLAYER_A: frozenset(), PLAYER_B: frozenset()},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    shutil.copy(result.log_path, event_log_path(run_dir=run_dir, scenario_name="signal_game"))
    [trajectory] = await build_agent_trajectories_from_run_dir(
        run_dir=run_dir,
        scenario_name="signal_game",
        agent_id=PLAYER_A,
        cutoff_round=None,
    )
    user_steps = [step for step in trajectory.steps if step.source is AtifStepSource.USER]
    prompts = runner_prompts_from_events(
        events=result.events, agent_id=PLAYER_A, role_name=PLAYER_A
    )
    assert [step.message for step in user_steps] == [
        prompts.initial,
        *briefings_for(result=result, agent_id=PLAYER_A),
    ]


async def test_a_briefing_cycle_that_fails_every_retry_restarts_with_its_briefing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Request 1 reads the first wake; requests 2 to 4 are the briefing cycle's three attempts.
    result, recorders = await play_two_rounds(
        failing={PLAYER_A: frozenset({2, 3, 4}), PLAYER_B: frozenset()},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert len(result.of_type(event_type=AgentRunCycleFailed)) == 1
    requests = recorders[PLAYER_A].requests
    first_briefing = briefings_for(result=result, agent_id=PLAYER_A)[0]
    failed = requests[1]
    restarted = requests[4]
    assert shape(messages=restarted) == shape(messages=failed)
    assert user_prompts(messages=restarted)[-1] == first_briefing


async def test_without_the_knob_the_briefing_stays_in_the_wait_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await play(
        scenario=build(preset_name="knobs_words", overrides={"round_count": 1}),
        scripts={
            PLAYER_A: [read(), end_round(), wait_for_next_round()],
            PLAYER_B: [read(), end_round(), wait_for_next_round()],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert result.of_type(event_type=CyclePromptSent) == []
    first_wake = next(
        json.loads(event.result)
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == PLAYER_A and event.tool_name == READ_NOTIFICATIONS_TOOL_NAME
    )
    assert first_wake["briefings"] == briefings_for(result=result, agent_id=PLAYER_A)
