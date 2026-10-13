"""A seat run by an agent CLI that connects to the run over MCP, in a real simulation.

The CLI is a stand-in that speaks MCP the way Claude Code and Codex do; the
tool server, the runner, the runtime, the tools and the event log all run for
real. What such a seat logs is what everything downstream reads, so the tests
assert against the log.
"""

import asyncio
import json
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from glossogen.cross_run_replace_agent import (
    CrossRunReplaceAgentRequest,
    prepare_cross_run_replace_agent_run,
)
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    CliTurnCompleted,
    HarnessSessionBound,
    MessageSent,
    SimulationEnded,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.replace_agent import ReplaceAgentRequest, prepare_replace_agent_run
from glossogen.runners.external_cli.cli_seat_runner import (
    MAX_CONSECUTIVE_TURN_FAILURES,
    ExternalCliRunner,
)
from glossogen.runners.harness_names import CLAUDE_CODE_HARNESS_NAME, PYDANTIC_AI_HARNESS_NAME
from glossogen.runners.harness_protocol import RunnerBuildContext
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import (
    RunnerSeat,
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
from tests.fakes.fake_mcp_cli import FakeAgentCli

ROUND_COUNT = 2


def send(text: str) -> dict[str, Any]:
    return {
        "call": {
            "tool": "send_message",
            "arguments": {"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        }
    }


def speak_then_idle(text: str) -> list[ScriptedTurn]:
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        ),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
    ]


async def no_pause(consecutive_failures: int) -> None:
    _ = consecutive_failures


async def run_with_cli_first_seat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    steps: list[dict[str, Any]],
) -> tuple[SimulationResult, FakeAgentCli]:
    """The first seat on the stand-in CLI, the second under pydantic-ai."""
    script_path = tmp_path / "cli_script.json"
    script_path.write_text(json.dumps(steps))
    cli = FakeAgentCli(script_path=script_path)

    def build_runner(context: RunnerBuildContext) -> ExternalCliRunner:
        return ExternalCliRunner(
            context=context,
            harness_name=CLAUDE_CODE_HARNESS_NAME,
            cli=cli,
            pause_after_failure=no_pause,
        )

    result = await run_mixed_harness_simulation(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(
                round_count=ROUND_COUNT, max_round_duration_seconds=45, model_overrides={}
            )
        ),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        runner_seats={
            FIRST_AGENT_ID: RunnerSeat(
                harness_name=CLAUDE_CODE_HARNESS_NAME, build_runner=build_runner
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    return result, cli


def of_first_agent(result: SimulationResult) -> list[Any]:
    return [event for event in result.events if getattr(event, "agent_id", None) == FIRST_AGENT_ID]


async def test_a_cli_seat_plays_a_whole_run_through_the_tools_it_connects_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, cli = await run_with_cli_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[send(text="from-first")],
    )

    assert result.of_type(event_type=SimulationEnded), "the run did not finish"
    harness_by_agent = {
        event.agent_id: event.harness for event in result.of_type(event_type=AgentRegistered)
    }
    assert harness_by_agent == {
        FIRST_AGENT_ID: CLAUDE_CODE_HARNESS_NAME,
        SECOND_AGENT_ID: PYDANTIC_AI_HARNESS_NAME,
    }
    sent_by_first = [
        event.message.text
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert sent_by_first == ["from-first"]
    first = of_first_agent(result=result)
    invoked = [event for event in first if isinstance(event, ToolCallInvoked)]
    returned = [event for event in first if isinstance(event, ToolResultReceived)]
    assert [event.tool_name for event in invoked][:1] == ["send_message"]
    assert {event.call_id for event in returned} == {event.call_id for event in invoked}
    assert "read_notifications" in {event.tool_name for event in invoked}
    bound = [event for event in first if isinstance(event, HarnessSessionBound)]
    assert [event.session_id for event in bound] == [f"session-{FIRST_AGENT_ID}"]
    turns = [event for event in first if isinstance(event, CliTurnCompleted)]
    assert turns, "the CLI's turn was not logged"
    assert turns[0].usage.input_tokens == 100
    assert turns[0].exit_code == 0
    assert not turns[0].is_error
    assert not [event for event in first if isinstance(event, AgentRunCycleFailed)]
    seat = cli.prepared[0]
    assert seat.agent_id == FIRST_AGENT_ID
    assert seat.tool_url.startswith("http://127.0.0.1:")
    assert seat.workspace.is_dir()
    kept = seat.state_dir.parent / "transcripts" / "nested" / f"session-{FIRST_AGENT_ID}.jsonl"
    assert kept.is_file(), "the CLI's transcript was not copied out beside its state"
    assert (seat.state_dir / "turns" / "turn-1.stdout").is_file()


async def test_a_turn_the_cli_ends_early_is_followed_by_a_continuation_on_the_same_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await run_with_cli_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[send(text="first-turn"), {"say": "stopping early"}, send(text="second-turn")],
    )

    sent_by_first = [
        event.message.text
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert sent_by_first == ["first-turn", "second-turn"]
    first = of_first_agent(result=result)
    turns = [event for event in first if isinstance(event, CliTurnCompleted)]
    assert len(turns) >= 2
    assert {event.session_id for event in turns} == {f"session-{FIRST_AGENT_ID}"}
    bound = [event for event in first if isinstance(event, HarnessSessionBound)]
    assert len(bound) == 1, "a resumed session is not bound again"


async def test_a_turn_whose_process_fails_is_logged_and_the_next_turn_carries_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await run_with_cli_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[{"exit": 3}, {"garbage": True}, send(text="after-failures")],
    )

    first = of_first_agent(result=result)
    failures = [event for event in first if isinstance(event, AgentRunCycleFailed)]
    assert [event.error_type for event in failures] == ["CliTurnFailed", "CliTurnFailed"]
    assert "exit code 3" in failures[0].message
    assert "not JSON" in failures[1].message
    sent_by_first = [
        event.message.text
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert sent_by_first == ["after-failures"]


async def test_a_cli_that_keeps_failing_stops_the_seat_and_the_run_carries_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _ = await run_with_cli_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[{"exit": 1}] * MAX_CONSECUTIVE_TURN_FAILURES + [send(text="never")],
    )

    first = of_first_agent(result=result)
    failures = [event for event in first if isinstance(event, AgentRunCycleFailed)]
    assert len(failures) == MAX_CONSECUTIVE_TURN_FAILURES
    assert not [
        event
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert result.of_type(event_type=SimulationEnded), "the other seat did not finish the run"


async def test_a_refused_tool_call_reaches_the_cli_as_the_tools_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``ValueError`` from an executor is the error the model reads, as under pydantic-ai."""
    result, _ = await run_with_cli_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[
            {
                "call": {
                    "tool": "read_channel",
                    "arguments": {"channel_id": "no-such-channel", "last_n": 5},
                }
            },
            send(text="after-refusal"),
        ],
    )

    first = of_first_agent(result=result)
    refused = [
        event
        for event in first
        if isinstance(event, ToolResultReceived) and event.tool_name == "read_channel"
    ]
    assert refused and "no-such-channel" in refused[0].result
    assert result.of_type(event_type=SimulationEnded)


async def test_the_tool_endpoint_refuses_a_connection_without_the_seats_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes: list[Future[int]] = []
    script_path = tmp_path / "cli_script.json"
    script_path.write_text(json.dumps([send(text="hello")]))

    def probe(url: str) -> int:
        return httpx2.post(
            url,
            headers={"Authorization": "Bearer not-the-token"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        ).status_code

    class ProbingCli(FakeAgentCli):
        def prepare(self, seat: Any) -> None:
            """Probe from a thread: the server runs on the loop ``prepare`` is called from."""
            super().prepare(seat)
            probes.append(executor.submit(probe, seat.tool_url))

    executor = ThreadPoolExecutor(max_workers=1)
    cli = ProbingCli(script_path=script_path)

    def build_runner(context: RunnerBuildContext) -> ExternalCliRunner:
        return ExternalCliRunner(
            context=context,
            harness_name=CLAUDE_CODE_HARNESS_NAME,
            cli=cli,
            pause_after_failure=no_pause,
        )

    result = await run_mixed_harness_simulation(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(
                round_count=ROUND_COUNT, max_round_duration_seconds=45, model_overrides={}
            )
        ),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        runner_seats={
            FIRST_AGENT_ID: RunnerSeat(
                harness_name=CLAUDE_CODE_HARNESS_NAME, build_runner=build_runner
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    assert [future.result() for future in probes] == [401]
    executor.shutdown()
    assert result.of_type(event_type=SimulationEnded)


async def test_the_endpoint_lists_the_seats_tools_with_the_schemas_the_log_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a CLI sees when it lists the tools is what ``agent_registered`` recorded."""
    listed: dict[str, dict[str, Any]] = {}
    listings: list[asyncio.Task[None]] = []
    script_path = tmp_path / "cli_script.json"
    script_path.write_text(json.dumps([send(text="hello")]))

    async def list_tools(url: str, token: str) -> None:
        http_client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})
        async with (
            http_client,
            streamable_http_client(url, http_client=http_client) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            for tool in (await session.list_tools()).tools:
                listed[tool.name] = tool.input_schema

    class ListingCli(FakeAgentCli):
        def prepare(self, seat: Any) -> None:
            """List from a task: ``prepare`` runs on the loop the server serves from."""
            super().prepare(seat)
            listings.append(asyncio.create_task(list_tools(seat.tool_url, seat.tool_token)))

    cli = ListingCli(script_path=script_path)

    def build_runner(context: RunnerBuildContext) -> ExternalCliRunner:
        return ExternalCliRunner(
            context=context,
            harness_name=CLAUDE_CODE_HARNESS_NAME,
            cli=cli,
            pause_after_failure=no_pause,
        )

    result = await run_mixed_harness_simulation(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(
                round_count=ROUND_COUNT, max_round_duration_seconds=45, model_overrides={}
            )
        ),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        runner_seats={
            FIRST_AGENT_ID: RunnerSeat(
                harness_name=CLAUDE_CODE_HARNESS_NAME, build_runner=build_runner
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    await asyncio.gather(*listings)

    registered = next(
        event
        for event in result.of_type(event_type=AgentRegistered)
        if event.agent_id == FIRST_AGENT_ID
    )
    recorded = {
        definition.name: definition.input_schema for definition in registered.tool_definitions
    }
    assert set(listed) == set(registered.tool_names)
    for name, schema in listed.items():
        assert set(schema.get("properties", {})) == set(recorded[name].get("properties", {})), name
        assert schema.get("required", []) == recorded[name].get("required", []), name


def smoke_class(name: str) -> type[SmokeScenario]:
    assert name == "smoke"
    return SmokeScenario


async def test_a_run_with_a_cli_seat_cannot_be_forked_keeping_that_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its conversation is the CLI's, and its log holds no responses to rebuild from."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    await run_with_cli_first_seat(
        tmp_path=source_dir, monkeypatch=monkeypatch, steps=[send(text="from-first")]
    )
    monkeypatch.setattr("glossogen.replace_agent.get_scenario_class", smoke_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def fork_request(replaced_agent_id: str | None) -> ReplaceAgentRequest:
        model: str | None = None
        provider: str | None = None
        harness: str | None = None
        visible: list[str] | None = None
        if replaced_agent_id is not None:
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

    with pytest.raises(ValueError, match=rf"{FIRST_AGENT_ID} \({CLAUDE_CODE_HARNESS_NAME}\)"):
        await prepare_replace_agent_run(request=fork_request(replaced_agent_id=None))
    prepared = await prepare_replace_agent_run(
        request=fork_request(replaced_agent_id=FIRST_AGENT_ID)
    )
    assert prepared.new_run_dir.exists()


async def test_a_cross_run_import_refuses_a_cli_seat_whether_kept_or_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources: list[Path] = []
    for name in ("source_a", "source_b"):
        source_dir = tmp_path / name
        source_dir.mkdir()
        await run_with_cli_first_seat(
            tmp_path=source_dir, monkeypatch=monkeypatch, steps=[send(text="from-first")]
        )
        sources.append(source_dir)
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

    with pytest.raises(ValueError, match=rf"{FIRST_AGENT_ID} \({CLAUDE_CODE_HARNESS_NAME}\)"):
        await prepare_cross_run_replace_agent_run(
            request=import_request(replaced_agent_id=SECOND_AGENT_ID)
        )
    with pytest.raises(ValueError, match="no llm_response_received events"):
        await prepare_cross_run_replace_agent_run(
            request=import_request(replaced_agent_id=FIRST_AGENT_ID)
        )


async def test_a_replacement_onto_a_cli_harness_is_refused(tmp_path: Path) -> None:
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
                harness=CLAUDE_CODE_HARNESS_NAME,
                knobs=None,
                channels_with_visible_history=[],
                channel_history_floors={},
                runs_dir=tmp_path / "runs",
            )
        )
