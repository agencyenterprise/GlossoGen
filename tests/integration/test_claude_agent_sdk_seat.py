"""A seat under the Claude Agent SDK harness, in a real simulation.

The seat's session is scripted, the way a pydantic-ai seat's model is: the
runtime, the tools, the clock and the event log all run for real. What a seat
logs under this harness is what everything downstream reads, so the tests
assert against the log: it has to say the same things about the seat that a
pydantic-ai seat's log would.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from glossogen.cross_run_replace_agent import (
    CrossRunReplaceAgentRequest,
    prepare_cross_run_replace_agent_run,
)
from glossogen.message_history_builder import build_message_history
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    HarnessSessionBound,
    LLMResponseReceived,
    MessageSent,
    SimulationEnded,
    ToolCallInvoked,
    ToolResultReceived,
    WaitRegistered,
)
from glossogen.replace_agent import ReplaceAgentRequest, prepare_replace_agent_run
from glossogen.runners.communication_protocol import platform_runner_prompts
from glossogen.runners.harness_names import (
    CLAUDE_AGENT_SDK_HARNESS_NAME,
    PYDANTIC_AI_HARNESS_NAME,
)
from glossogen.runners.session_harness.runner import (
    FAILURE_PAUSE_BASE_SECONDS,
    FAILURE_PAUSE_MAX_SECONDS,
    MAX_CONSECUTIVE_SESSION_FAILURES,
    failure_pause_seconds,
)
from glossogen.testing.scripted_agent import (
    SayTurn,
    ScriptedTurn,
    ToolTurn,
    scripted_turn_source,
)
from glossogen.testing.scripted_seat_session import (
    SCRIPTED_USAGE,
    FailedTurn,
    ParallelToolTurn,
    ScriptedSeatSession,
    SeatTurn,
    SessionCrash,
)
from glossogen.testing.simulation_harness import (
    IDLE_CYCLE,
    SessionSeat,
    SimulationResult,
    never_times_out,
    run_mixed_harness_simulation,
    run_simulation,
    scripted_session_seat,
)
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

ROUND_COUNT = 2


def build_scenario() -> SmokeScenario:
    """The smoke scenario for two rounds."""
    return SmokeScenario(
        knobs=SmokeKnobs(
            round_count=ROUND_COUNT,
            max_round_duration_seconds=45,
            model_overrides={},
        )
    )


def speak_then_idle(text: str) -> list[ScriptedTurn]:
    """One send, then park until something happens."""
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        ),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
    ]


async def run_with_sdk_first_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first_seat_script: list[SeatTurn]
) -> SimulationResult:
    """The first seat under the SDK harness on its script, the second under pydantic-ai."""
    return await run_mixed_harness_simulation(
        scenario=build_scenario(),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        session_seats={
            FIRST_AGENT_ID: scripted_session_seat(
                agent_id=FIRST_AGENT_ID,
                turns=first_seat_script,
                harness_name=CLAUDE_AGENT_SDK_HARNESS_NAME,
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def of_agent(events: list[Any], agent_id: str) -> list[Any]:
    """The events ``agent_id`` itself caused."""
    return [event for event in events if getattr(event, "agent_id", None) == agent_id]


async def test_a_mixed_run_finishes_with_each_seat_recorded_under_its_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        first_seat_script=list(speak_then_idle(text="from-first") * ROUND_COUNT),
    )

    assert result.of_type(event_type=SimulationEnded), "the run did not finish"
    harness_by_agent = {
        event.agent_id: event.harness for event in result.of_type(event_type=AgentRegistered)
    }
    assert harness_by_agent == {
        FIRST_AGENT_ID: CLAUDE_AGENT_SDK_HARNESS_NAME,
        SECOND_AGENT_ID: PYDANTIC_AI_HARNESS_NAME,
    }
    sent_by_first = [
        event.message.text
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert sent_by_first == ["from-first"] * ROUND_COUNT
    bound = result.of_type(event_type=HarnessSessionBound)
    assert [(event.agent_id, event.session_id) for event in bound] == [
        (FIRST_AGENT_ID, f"scripted-{FIRST_AGENT_ID}")
    ]


async def test_every_sdk_response_is_logged_with_its_own_usage_and_paired_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each call in a response has an invocation and a result under the same id."""
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        first_seat_script=list(speak_then_idle(text="from-first") * ROUND_COUNT),
    )

    first = of_agent(events=result.events, agent_id=FIRST_AGENT_ID)
    responses = [event for event in first if isinstance(event, LLMResponseReceived)]
    assert responses
    assert all(response.usage == SCRIPTED_USAGE for response in responses)
    called = [call.call_id for response in responses for call in response.tool_calls]
    invoked = [event.call_id for event in first if isinstance(event, ToolCallInvoked)]
    returned = [event.call_id for event in first if isinstance(event, ToolResultReceived)]
    assert sorted(called) == sorted(invoked)
    assert set(returned) <= set(invoked)
    assert not [event for event in first if isinstance(event, AgentRunCycleFailed)]


async def test_an_sdk_seat_makes_the_same_calls_its_script_makes_under_pydantic_ai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One script, either harness: the log shows the same calls in the same order."""
    script = speak_then_idle(text="from-first") * ROUND_COUNT
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()
    pydantic_dir = tmp_path / "pydantic"
    pydantic_dir.mkdir()
    under_sdk = await run_with_sdk_first_seat(
        tmp_path=sdk_dir, monkeypatch=monkeypatch, first_seat_script=list(script)
    )
    under_pydantic = await run_simulation(
        scenario=build_scenario(),
        scripts={
            FIRST_AGENT_ID: script,
            SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT,
        },
        tmp_path=pydantic_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    def calls(result: SimulationResult) -> list[tuple[str, dict[str, Any]]]:
        return [
            (event.tool_name, event.arguments)
            for event in result.of_type(event_type=ToolCallInvoked)
            if event.agent_id == FIRST_AGENT_ID
        ]

    assert (
        calls(result=under_sdk)[: len(script) - 1]
        == calls(result=under_pydantic)[: len(script) - 1]
    )


async def test_an_sdk_seats_log_rebuilds_into_paired_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The history rebuilder reads an SDK seat's log the way it reads any seat's."""
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        first_seat_script=list(speak_then_idle(text="from-first") * ROUND_COUNT),
    )
    registration = next(
        event
        for event in result.of_type(event_type=AgentRegistered)
        if event.agent_id == FIRST_AGENT_ID
    )

    history = build_message_history(
        events=result.events,
        agent_id=FIRST_AGENT_ID,
        system_prompt=registration.system_prompt,
        runner_prompts=platform_runner_prompts(role_name=registration.role_name),
        target_timestamp=result.events[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=False,
        channel_visibility={},
        filter_below_round=None,
        split_parallel_tool_calls=False,
    )

    rebuilt_calls = [
        part.tool_name
        for message in history
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    assert rebuilt_calls[:2] == ["send_message", "read_notifications"]


async def test_a_wait_issued_beside_another_call_is_refused_without_parking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI runs each call as soon as it streams, so the response is checked once complete."""
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        first_seat_script=[
            ParallelToolTurn(
                calls=(
                    ToolTurn(tool_name="read_notifications", args={}),
                    ToolTurn(tool_name="list_channels", args={}),
                )
            ),
            SayTurn(text="saw the refusal"),
            *speak_then_idle(text="from-first") * ROUND_COUNT,
        ],
    )

    first = of_agent(events=result.events, agent_id=FIRST_AGENT_ID)
    first_wait_result = next(
        event
        for event in first
        if isinstance(event, ToolResultReceived) and event.tool_name == "read_notifications"
    )
    assert "cannot be issued in parallel" in first_wait_result.result
    first_wait_logged_at = first.index(first_wait_result)
    assert not [
        event for event in first[:first_wait_logged_at] if isinstance(event, WaitRegistered)
    ]
    assert result.of_type(event_type=SimulationEnded)


async def test_a_session_that_crashes_is_reopened_and_the_seat_carries_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        first_seat_script=[
            SessionCrash(reason="the CLI process exited", mid_response=None),
            *speak_then_idle(text="from-first") * ROUND_COUNT,
        ],
    )

    failures = [
        event
        for event in result.of_type(event_type=AgentRunCycleFailed)
        if event.agent_id == FIRST_AGENT_ID
    ]
    assert [(event.error_type, event.message) for event in failures] == [
        ("ScriptedSessionCrashed", "the CLI process exited")
    ]
    sent_by_first = [
        event.message.text
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert sent_by_first == ["from-first"] * ROUND_COUNT


async def test_a_session_that_keeps_crashing_stops_the_seat_and_the_run_carries_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crash = SessionCrash(reason="the CLI process exited", mid_response=None)
    script: list[SeatTurn] = [crash] * MAX_CONSECUTIVE_SESSION_FAILURES
    script.extend(speak_then_idle(text="from-first") * ROUND_COUNT)
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path, monkeypatch=monkeypatch, first_seat_script=script
    )

    failures = [
        event
        for event in result.of_type(event_type=AgentRunCycleFailed)
        if event.agent_id == FIRST_AGENT_ID
    ]
    assert len(failures) == MAX_CONSECUTIVE_SESSION_FAILURES
    assert not [
        event
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert result.of_type(event_type=SimulationEnded), "the other seat did not finish the run"


async def test_a_turn_the_cli_reports_failed_is_logged_and_the_next_cycle_carries_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        first_seat_script=[
            FailedTurn(error_text="rate limited"),
            *speak_then_idle(text="from-first") * ROUND_COUNT,
        ],
    )

    failures = [
        (event.error_type, event.message)
        for event in result.of_type(event_type=AgentRunCycleFailed)
        if event.agent_id == FIRST_AGENT_ID
    ]
    assert failures == [("CycleEndedWithError", "rate limited")]
    sent_by_first = [
        event.message.text
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert sent_by_first == ["from-first"] * ROUND_COUNT


async def test_turns_that_keep_failing_stop_the_seat_instead_of_running_every_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad key or an unknown model fails every turn; the seat must not burn max_turns."""
    script: list[SeatTurn] = [FailedTurn(error_text="invalid x-api-key")] * (
        MAX_CONSECUTIVE_SESSION_FAILURES
    )
    script.extend(speak_then_idle(text="from-first") * ROUND_COUNT)
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path, monkeypatch=monkeypatch, first_seat_script=script
    )

    failures = [
        event
        for event in result.of_type(event_type=AgentRunCycleFailed)
        if event.agent_id == FIRST_AGENT_ID
    ]
    assert len(failures) == MAX_CONSECUTIVE_SESSION_FAILURES
    assert not [
        event
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert result.of_type(event_type=SimulationEnded)


class TurnAlreadyEndedSession(ScriptedSeatSession):
    """A session whose interrupt comes too late, as a CLI's does when the turn already ended."""

    async def interrupt(self) -> None:
        raise RuntimeError('{"code": -32600, "message": "no active turn to interrupt"}')


async def test_an_interrupt_refused_after_the_run_ended_is_not_a_failed_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    take_turn = scripted_turn_source(
        turns=list(speak_then_idle(text="from-first") * ROUND_COUNT),
        when_exhausted=IDLE_CYCLE,
    )

    def late_interrupt_session() -> TurnAlreadyEndedSession:
        return TurnAlreadyEndedSession(take_turn=take_turn, session_id="late-interrupt")

    result = await run_mixed_harness_simulation(
        scenario=build_scenario(),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        session_seats={
            FIRST_AGENT_ID: SessionSeat(
                harness_name=CLAUDE_AGENT_SDK_HARNESS_NAME, session_factory=late_interrupt_session
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    assert result.of_type(event_type=SimulationEnded)
    assert not [
        event
        for event in result.of_type(event_type=AgentRunCycleFailed)
        if event.agent_id == FIRST_AGENT_ID
    ]


async def test_a_run_with_an_sdk_seat_cannot_be_forked_keeping_that_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its conversation is in the CLI's transcript, which a pydantic-ai history cannot seed."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    await run_with_sdk_first_seat(
        tmp_path=source_dir,
        monkeypatch=monkeypatch,
        first_seat_script=list(speak_then_idle(text="from-first") * ROUND_COUNT),
    )

    def smoke_class(name: str) -> type[SmokeScenario]:
        assert name == "smoke"
        return SmokeScenario

    monkeypatch.setattr("glossogen.replace_agent.get_scenario_class", smoke_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def fork_request(replaced_agent_id: str | None) -> ReplaceAgentRequest:
        replacing = replaced_agent_id is not None
        model: str | None = None
        provider: str | None = None
        harness: str | None = None
        visible: list[str] | None = None
        if replacing:
            model = "claude-sonnet-4-6"
            provider = "anthropic"
            harness = PYDANTIC_AI_HARNESS_NAME
            visible = []
        return ReplaceAgentRequest(
            source_run_dir=source_dir,
            scenario_name="smoke",
            after_round=1,
            rounds_after=1,
            replaced_agent_id=replaced_agent_id,
            model=model,
            provider=provider,
            harness=harness,
            knobs=None,
            channels_with_visible_history=visible,
            channel_history_floors={},
            runs_dir=tmp_path / "runs",
        )

    with pytest.raises(ValueError, match=rf"{FIRST_AGENT_ID} \({CLAUDE_AGENT_SDK_HARNESS_NAME}\)"):
        await prepare_replace_agent_run(request=fork_request(replaced_agent_id=None))

    prepared = await prepare_replace_agent_run(
        request=fork_request(replaced_agent_id=FIRST_AGENT_ID)
    )
    assert prepared.new_run_dir.exists()


async def test_a_cross_run_import_refuses_keeping_a_cli_seat_but_imports_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Source A's kept seats must rebuild; source B's imported seat always can."""
    sources: list[Path] = []
    for name in ("source_a", "source_b"):
        source_dir = tmp_path / name
        source_dir.mkdir()
        await run_with_sdk_first_seat(
            tmp_path=source_dir,
            monkeypatch=monkeypatch,
            first_seat_script=list(speak_then_idle(text="from-first") * ROUND_COUNT),
        )
        sources.append(source_dir)

    def smoke_class(name: str) -> type[SmokeScenario]:
        assert name == "smoke"
        return SmokeScenario

    monkeypatch.setattr("glossogen.cross_run_replace_agent.get_scenario_class", smoke_class)
    monkeypatch.setattr("glossogen.replace_agent.get_scenario_class", smoke_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def import_request(replaced_agent_id: str) -> CrossRunReplaceAgentRequest:
        return CrossRunReplaceAgentRequest(
            source_a_run_dir=sources[0],
            source_b_run_dir=sources[1],
            scenario_name="smoke",
            after_round=1,
            source_b_round_end=1,
            rounds_after=1,
            replaced_agent_id=replaced_agent_id,
            model="claude-sonnet-4-6",
            provider="anthropic",
            harness=PYDANTIC_AI_HARNESS_NAME,
            knobs=None,
            channels_with_visible_history=[],
            runs_dir=tmp_path / "runs",
        )

    with pytest.raises(ValueError, match=rf"{FIRST_AGENT_ID} \({CLAUDE_AGENT_SDK_HARNESS_NAME}\)"):
        await prepare_cross_run_replace_agent_run(
            request=import_request(replaced_agent_id=SECOND_AGENT_ID)
        )

    prepared = await prepare_cross_run_replace_agent_run(
        request=import_request(replaced_agent_id=FIRST_AGENT_ID)
    )
    assert prepared.new_run_dir.exists()


async def test_a_replacement_onto_the_sdk_harness_is_refused(tmp_path: Path) -> None:
    """A replacement seeds the seat with a rebuilt history, which only pydantic-ai takes."""
    with pytest.raises(ValueError, match="reconstructed history"):
        await prepare_replace_agent_run(
            request=ReplaceAgentRequest(
                source_run_dir=tmp_path,
                scenario_name="smoke",
                after_round=1,
                rounds_after=1,
                replaced_agent_id=FIRST_AGENT_ID,
                model="claude-sonnet-4-6",
                provider="anthropic",
                harness=CLAUDE_AGENT_SDK_HARNESS_NAME,
                knobs=None,
                channels_with_visible_history=[],
                channel_history_floors={},
                runs_dir=tmp_path / "runs",
            )
        )


async def test_a_crash_mid_response_still_logs_the_response_that_issued_the_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A call logged without its response would be rebuilt as an orphan turn."""
    result = await run_with_sdk_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        first_seat_script=[
            SessionCrash(
                reason="the CLI process exited",
                mid_response=ToolTurn(tool_name="list_channels", args={}),
            ),
            *speak_then_idle(text="from-first") * ROUND_COUNT,
        ],
    )

    first = of_agent(events=result.events, agent_id=FIRST_AGENT_ID)
    parented = {
        call.call_id
        for event in first
        if isinstance(event, LLMResponseReceived)
        for call in event.tool_calls
    }
    invoked = [event.call_id for event in first if isinstance(event, ToolCallInvoked)]
    assert invoked
    assert set(invoked) <= parented
    bound = [event for event in first if isinstance(event, HarnessSessionBound)]
    failed = [event for event in first if isinstance(event, AgentRunCycleFailed)]
    assert first.index(bound[0]) < first.index(failed[0]), "the session was bound before it died"
    assert result.of_type(event_type=SimulationEnded)


async def test_a_fork_cannot_move_a_kept_seat_onto_the_sdk_harness_through_its_knobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every seat a fork keeps is seeded with a rebuilt history."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    await run_simulation(
        scenario=build_scenario(),
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="from-first") * ROUND_COUNT,
            SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT,
        },
        tmp_path=source_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    def smoke_class(name: str) -> type[SmokeScenario]:
        assert name == "smoke"
        return SmokeScenario

    monkeypatch.setattr("glossogen.replace_agent.get_scenario_class", smoke_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with pytest.raises(ValueError, match="reconstructed history"):
        await prepare_replace_agent_run(
            request=ReplaceAgentRequest(
                source_run_dir=source_dir,
                scenario_name="smoke",
                after_round=1,
                rounds_after=1,
                replaced_agent_id=None,
                model=None,
                provider=None,
                harness=None,
                knobs={
                    "model_overrides": {
                        SECOND_AGENT_ID: {
                            "model": "claude-sonnet-4-6",
                            "provider": "anthropic",
                            "harness": CLAUDE_AGENT_SDK_HARNESS_NAME,
                        }
                    }
                },
                channels_with_visible_history=None,
                channel_history_floors={},
                runs_dir=tmp_path / "runs",
            )
        )


def test_the_pause_after_a_failed_cycle_doubles_and_is_capped() -> None:
    """Back-to-back failures would end a seat within milliseconds of an outage."""
    assert [failure_pause_seconds(consecutive_failures=n) for n in range(1, 6)] == [
        FAILURE_PAUSE_BASE_SECONDS,
        FAILURE_PAUSE_BASE_SECONDS * 2,
        FAILURE_PAUSE_MAX_SECONDS,
        FAILURE_PAUSE_MAX_SECONDS,
        FAILURE_PAUSE_MAX_SECONDS,
    ]
