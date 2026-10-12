"""What ``SessionSeatRunner`` does with what a session reports, beyond a scripted agent's turns.

Each test hands the first seat a session of its own for the first turn, then a
scripted session, so the runtime, the tools and the event log run for real and
the log shows what the runner made of the session's items.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import cast

import pytest

from glossogen.event_bus import EventBus
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.compaction_config import CompactionConfig
from glossogen.models.event import (
    AgentRunCycleFailed,
    LLMResponseReceived,
    SimulationEnded,
    ToolResultReceived,
)
from glossogen.runners.agent_tools import ToolOutcome
from glossogen.runners.harness_names import CLAUDE_AGENT_SDK_HARNESS_NAME
from glossogen.runners.harness_protocol import RunnerBuildContext
from glossogen.runners.session_harness.runner import (
    MAX_CONSECUTIVE_SESSION_FAILURES,
    SessionSeatRunner,
)
from glossogen.runners.session_harness.seat_session import (
    CycleEnded,
    ResponseCompleted,
    ResponseStarted,
    SeatOptions,
    SeatSession,
    SeatToolCall,
    SessionItem,
    SessionStarted,
    TextChunk,
    ThinkingChunk,
    ToolResultChunk,
    ToolUseChunk,
)
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn, scripted_turn_source
from glossogen.testing.scripted_seat_session import SCRIPTED_USAGE, ScriptedSeatSession
from glossogen.testing.simulation_harness import (
    IDLE_CYCLE,
    SCRIPTED_SEAT_CLOCK,
    SessionSeat,
    SimulationResult,
    never_times_out,
    run_mixed_harness_simulation,
)
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

ROUND_COUNT = 2
SESSION_ID = "custom-session"


def speak_then_idle(text: str) -> list[ScriptedTurn]:
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        ),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
    ]


def ended(is_error: bool) -> CycleEnded:
    return CycleEnded(
        session_id=SESSION_ID, is_error=is_error, error_text="", reported_cost_usd=None
    )


class FirstTurnSession:
    """Plays ``first_turn`` as its first cycle, then a scripted session's turns.

    ``first_turn`` may raise, which the runner reads as the session crashing.
    """

    def __init__(
        self,
        first_turn: Callable[[SeatOptions], AsyncIterator[SessionItem]],
        scripted: ScriptedSeatSession,
    ) -> None:
        self._first_turn = first_turn
        self._scripted = scripted
        self._options: SeatOptions | None = None
        self._turns = 0

    async def connect(self, options: SeatOptions) -> None:
        self._options = options
        await self._scripted.connect(options=options)

    async def send(self, prompt: str) -> None:
        self._turns += 1
        await self._scripted.send(prompt=prompt)

    async def items(self) -> AsyncIterator[SessionItem]:
        if self._turns == 1 and self._options is not None:
            async for item in self._first_turn(self._options):
                yield item
            return
        async for item in self._scripted.items():
            yield item

    async def interrupt(self) -> None:
        await self._scripted.interrupt()

    async def close(self) -> None:
        await self._scripted.close()


async def run_with_first_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_turn: Callable[[SeatOptions], AsyncIterator[SessionItem]],
    knobs: SmokeKnobs,
) -> SimulationResult:
    """The first seat on a session whose first turn is ``first_turn``; later ones are scripted."""
    take_turn = scripted_turn_source(
        turns=speak_then_idle(text="from-first") * ROUND_COUNT, when_exhausted=IDLE_CYCLE
    )
    opened = 0

    def session() -> SeatSession:
        nonlocal opened
        opened += 1
        scripted = ScriptedSeatSession(take_turn=take_turn, session_id=SESSION_ID)
        if opened == 1:
            return FirstTurnSession(first_turn=first_turn, scripted=scripted)
        return scripted

    return await run_mixed_harness_simulation(
        scenario=SmokeScenario(knobs=knobs),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        session_seats={
            FIRST_AGENT_ID: SessionSeat(
                harness_name=CLAUDE_AGENT_SDK_HARNESS_NAME,
                session_factory=session,
                clock=SCRIPTED_SEAT_CLOCK,
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def smoke_knobs() -> SmokeKnobs:
    return SmokeKnobs(round_count=ROUND_COUNT, max_round_duration_seconds=45, model_overrides={})


def of_first_agent(result: SimulationResult) -> list[object]:
    return [event for event in result.events if getattr(event, "agent_id", None) == FIRST_AGENT_ID]


async def test_a_responses_thinking_is_logged_with_the_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def thinking_turn(options: SeatOptions) -> AsyncIterator[SessionItem]:
        _ = options
        yield SessionStarted(session_id=SESSION_ID)
        yield ResponseStarted(message_id="m1")
        yield ThinkingChunk(
            message_id="m1", thinking="Plan the send.", signature="sig", provider_name="anthropic"
        )
        yield TextChunk(message_id="m1", text="ok")
        yield ResponseCompleted(message_id="m1", stop_reason="end_turn", usage=SCRIPTED_USAGE)
        yield ended(is_error=False)

    result = await run_with_first_turn(
        tmp_path=tmp_path, monkeypatch=monkeypatch, first_turn=thinking_turn, knobs=smoke_knobs()
    )

    responses = [e for e in of_first_agent(result=result) if isinstance(e, LLMResponseReceived)]
    assert responses[0].thinking == "Plan the send."
    assert responses[0].text == "ok"
    assert [(part.content, part.signature) for part in responses[0].thinking_parts] == [
        ("Plan the send.", "sig")
    ]
    assert result.of_type(event_type=SimulationEnded)


async def test_a_result_for_a_call_the_runner_never_saw_is_logged_as_a_warning_and_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def stray_result(options: SeatOptions) -> AsyncIterator[SessionItem]:
        _ = options
        yield SessionStarted(session_id=SESSION_ID)
        yield ResponseStarted(message_id="m1")
        yield TextChunk(message_id="m1", text="ok")
        yield ToolResultChunk(call_id="ghost", content="from nowhere")
        yield ResponseCompleted(message_id="m1", stop_reason="end_turn", usage=SCRIPTED_USAGE)
        yield ended(is_error=False)

    with caplog.at_level(logging.WARNING, logger="glossogen.runners.session_harness.runner"):
        result = await run_with_first_turn(
            tmp_path=tmp_path, monkeypatch=monkeypatch, first_turn=stray_result, knobs=smoke_knobs()
        )

    assert "got a result for unknown call ghost" in caplog.text
    results = [e for e in of_first_agent(result=result) if isinstance(e, ToolResultReceived)]
    assert "ghost" not in {event.call_id for event in results}
    assert not [e for e in of_first_agent(result=result) if isinstance(e, AgentRunCycleFailed)]


async def test_a_session_that_stops_reporting_before_the_turn_ends_fails_the_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every reopened session stops the same way, so the seat gives up after the limit."""
    take_turn = scripted_turn_source(turns=[], when_exhausted=IDLE_CYCLE)

    async def silent(options: SeatOptions) -> AsyncIterator[SessionItem]:
        _ = options
        yield SessionStarted(session_id=SESSION_ID)

    def session() -> SeatSession:
        return FirstTurnSession(
            first_turn=silent,
            scripted=ScriptedSeatSession(take_turn=take_turn, session_id=SESSION_ID),
        )

    result = await run_mixed_harness_simulation(
        scenario=SmokeScenario(knobs=smoke_knobs()),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        session_seats={
            FIRST_AGENT_ID: SessionSeat(
                harness_name=CLAUDE_AGENT_SDK_HARNESS_NAME,
                session_factory=session,
                clock=SCRIPTED_SEAT_CLOCK,
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    failures = [e for e in of_first_agent(result=result) if isinstance(e, AgentRunCycleFailed)]
    assert [event.message for event in failures] == [
        "the session stopped reporting before the turn ended"
    ] * MAX_CONSECUTIVE_SESSION_FAILURES
    assert result.of_type(event_type=SimulationEnded), "the other seat did not finish the run"


async def test_a_wait_whose_session_dies_while_it_waits_is_answered_rather_than_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The handler was waiting for its response to settle; the crash settles it as abandoned."""
    outcomes: list[asyncio.Task[ToolOutcome]] = []

    async def dies_mid_call(options: SeatOptions) -> AsyncIterator[SessionItem]:
        wait = next(tool for tool in options.tools if tool.name == "read_notifications")
        yield SessionStarted(session_id=SESSION_ID)
        yield ResponseStarted(message_id="m1")
        yield ToolUseChunk(
            message_id="m1",
            call_id="c1",
            tool_name="read_notifications",
            arguments={},
            answered_by_cli=False,
        )

        async def run_wait() -> ToolOutcome:
            return await wait.handler(SeatToolCall(call_id=None, arguments={}))

        outcomes.append(asyncio.create_task(run_wait()))
        await asyncio.sleep(0)
        raise RuntimeError("the CLI died mid-call")

    result = await run_with_first_turn(
        tmp_path=tmp_path, monkeypatch=monkeypatch, first_turn=dies_mid_call, knobs=smoke_knobs()
    )

    assert await outcomes[0] == ToolOutcome(
        content="The response that issued this call ended before it completed.", is_error=True
    )
    failures = [e for e in of_first_agent(result=result) if isinstance(e, AgentRunCycleFailed)]
    assert [event.message for event in failures] == ["the CLI died mid-call"]
    assert result.of_type(event_type=SimulationEnded)


async def test_invalid_wait_arguments_are_refused_in_the_tools_own_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    take_turn = scripted_turn_source(
        turns=[
            ToolTurn(tool_name="read_notifications", args={"wait_for": "never"}),
            *speak_then_idle(text="from-first") * ROUND_COUNT,
        ],
        when_exhausted=IDLE_CYCLE,
    )

    def session() -> SeatSession:
        return ScriptedSeatSession(take_turn=take_turn, session_id=SESSION_ID)

    result = await run_mixed_harness_simulation(
        scenario=SmokeScenario(knobs=smoke_knobs()),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        session_seats={
            FIRST_AGENT_ID: SessionSeat(
                harness_name=CLAUDE_AGENT_SDK_HARNESS_NAME,
                session_factory=session,
                clock=SCRIPTED_SEAT_CLOCK,
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    results = [e for e in of_first_agent(result=result) if isinstance(e, ToolResultReceived)]
    assert results[0].tool_name == "read_notifications"
    assert "Invalid arguments for read_notifications" in results[0].result
    assert result.of_type(event_type=SimulationEnded)


async def test_a_seat_that_enables_compaction_is_warned_that_the_cli_compacts_instead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def plain(options: SeatOptions) -> AsyncIterator[SessionItem]:
        _ = options
        yield SessionStarted(session_id=SESSION_ID)
        yield ResponseStarted(message_id="m1")
        yield TextChunk(message_id="m1", text="ok")
        yield ResponseCompleted(message_id="m1", stop_reason="end_turn", usage=SCRIPTED_USAGE)
        yield ended(is_error=False)

    knobs = SmokeKnobs(
        round_count=ROUND_COUNT,
        max_round_duration_seconds=45,
        model_overrides={},
        compaction=CompactionConfig(enabled=True, token_threshold=60_000),
    )
    with caplog.at_level(logging.WARNING, logger="glossogen.runners.session_harness.runner"):
        await run_with_first_turn(
            tmp_path=tmp_path, monkeypatch=monkeypatch, first_turn=plain, knobs=knobs
        )

    assert f"Agent {FIRST_AGENT_ID} enables compaction, which claude-agent-sdk does not apply" in (
        caplog.text
    )


async def test_a_session_runner_refuses_a_seat_seeded_with_a_rebuilt_history(
    tmp_path: Path,
) -> None:
    """The launch check keeps such seats off this runner; one that got through is refused."""
    runner = SessionSeatRunner(
        context=RunnerBuildContext(
            max_turns=1,
            event_bus=EventBus(max_queue_size=10),
            run_id="run",
            scenario_name="smoke",
            telemetry_enabled=False,
            run_dir=tmp_path,
        ),
        session_factory=lambda: ScriptedSeatSession(
            take_turn=lambda: SayTurn(text="x"), session_id="s"
        ),
        harness_name=CLAUDE_AGENT_SDK_HARNESS_NAME,
        clock=SCRIPTED_SEAT_CLOCK,
    )
    seeded = AgentConfig(
        agent_id=FIRST_AGENT_ID,
        role_name="first",
        system_prompt="",
        channel_ids=[LINK_CHANNEL_ID],
        tool_names=[],
        model="claude-sonnet-4-6",
        provider=Provider.ANTHROPIC,
        harness=CLAUDE_AGENT_SDK_HARNESS_NAME,
        max_tokens=2048,
        compaction=CompactionConfig(),
        initial_message_history=[],
    )

    with pytest.raises(ValueError, match="cannot take the reconstructed history"):
        await runner.start(
            agent_config=seeded, runtime=cast(SimulationRuntime, object()), cost_tracker={}
        )
