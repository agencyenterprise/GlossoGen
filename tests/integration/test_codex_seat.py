"""A seat under the Codex harness, against a fake ``codex app-server``.

The fake speaks the app server's protocol in the order a live session does and
plays a scripted agent, so the connection, the translation and the session
runner all run for real, and so do the runtime, the tools and the event log.
Only the model is scripted.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from glossogen.model_catalog import Provider
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    ContextCompacted,
    HarnessSessionBound,
    LLMResponseReceived,
    MessageSent,
    SimulationEnded,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.runners.agent_tools import ToolOutcome
from glossogen.runners.codex_app_server.app_server_connection import AppServerExited
from glossogen.runners.codex_app_server.codex_item_translator import UNPARSED_ARGUMENTS_KEY
from glossogen.runners.codex_app_server.codex_seat_session import (
    CONFIG_OVERRIDES,
    DISABLED_FEATURES,
    CodexSeatSession,
)
from glossogen.runners.codex_app_server.harness import CodexAppServerHarness
from glossogen.runners.harness_names import (
    CODEX_HARNESS_NAME,
    HARNESS_STATE_DIR_NAME,
    PYDANTIC_AI_HARNESS_NAME,
)
from glossogen.runners.harness_protocol import HarnessSeat
from glossogen.runners.session_harness.seat_session import (
    CycleEnded,
    ResponseCompleted,
    SeatOptions,
    SeatTool,
    SessionItem,
    SessionStarted,
    ToolResultChunk,
    ToolUseChunk,
)
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import (
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
from tests.fakes import fake_codex_app_server

ROUND_COUNT = 2
FAKE_SERVER = (sys.executable, fake_codex_app_server.__file__)


def write_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, steps: list[dict[str, Any]]
) -> None:
    """Hand the fake server its agent's script."""
    script = tmp_path / "codex_script.json"
    script.write_text(json.dumps(steps))
    monkeypatch.setenv(fake_codex_app_server.SCRIPT_ENV, str(script))


def send(text: str) -> dict[str, Any]:
    return {
        "call": {
            "tool": "send_message",
            "arguments": {"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        }
    }


def speak_then_idle_steps(text: str) -> list[dict[str, Any]]:
    return [
        send(text=text),
        {"call": {"tool": "read_notifications", "arguments": {}}},
        {"say": "idle"},
    ]


def speak_then_idle(text: str) -> list[ScriptedTurn]:
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        ),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
    ]


async def echo(arguments: dict[str, Any]) -> ToolOutcome:
    return ToolOutcome(content=f"echoed {arguments['note']}", is_error=False)


async def refuse(arguments: dict[str, Any]) -> ToolOutcome:
    _ = arguments
    return ToolOutcome(content="you may not do that", is_error=True)


async def explode(arguments: dict[str, Any]) -> ToolOutcome:
    _ = arguments
    raise RuntimeError("the handler broke")


ECHO_SCHEMA = {
    "type": "object",
    "properties": {"note": {"type": "string"}},
    "required": ["note"],
}


async def test_a_session_runs_the_seats_tools_and_keeps_its_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a credential the seat must not use")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")
    write_script(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[
            {"call": {"tool": "echo_state", "arguments": {"note": "a"}}},
            {"call": {"tool": "refuse", "arguments": {}}},
            {"call": {"tool": "explode", "arguments": {}}},
            {"say": "done"},
        ],
    )
    seat_dir = tmp_path / "run" / "harness" / "field_observer"
    session = CodexSeatSession(launch_command=FAKE_SERVER)
    await session.connect(
        options=SeatOptions(
            model="gpt-5.4",
            system_prompt="You observe.",
            tools=(
                SeatTool(
                    name="echo_state", description="Echo.", input_schema=ECHO_SCHEMA, handler=echo
                ),
                SeatTool(
                    name="refuse",
                    description="Refuses.",
                    input_schema={"type": "object", "properties": {}},
                    handler=refuse,
                ),
                SeatTool(
                    name="explode",
                    description="Raises.",
                    input_schema={"type": "object", "properties": {}},
                    handler=explode,
                ),
            ),
            max_output_tokens=2048,
            seat_dir=seat_dir,
            resume_session_id=None,
        )
    )
    await session.send(prompt="Begin.")
    items: list[SessionItem] = [item async for item in session.items()]
    await session.close()

    assert items[0] == SessionStarted(session_id="fake-thread")
    assert [item.content for item in items if isinstance(item, ToolResultChunk)] == [
        "echoed a",
        "you may not do that",
        fake_codex_app_server.FAILED_TOOL_REQUEST_TEXT,
    ]
    assert [item.tool_name for item in items if isinstance(item, ToolUseChunk)] == [
        "echo_state",
        "refuse",
        "explode",
    ]
    assert len([item for item in items if isinstance(item, ResponseCompleted)]) == 4
    assert items[-1] == CycleEnded(
        session_id="fake-thread", is_error=False, error_text="", reported_cost_usd=None
    )

    record = json.loads(
        (
            seat_dir
            / HARNESS_STATE_DIR_NAME
            / "codex_home"
            / fake_codex_app_server.RECORD_FILE_NAME
        ).read_text()
    )
    thread_start = next(r["params"] for r in record["requests"] if r["method"] == "thread/start")
    assert thread_start["baseInstructions"] == "You observe."
    assert [tool["name"] for tool in thread_start["dynamicTools"]] == [
        "echo_state",
        "refuse",
        "explode",
    ]
    assert thread_start["experimentalRawEvents"] is True
    for feature in DISABLED_FEATURES:
        assert ["--disable", feature] == record["argv"][record["argv"].index(feature) - 1 :][:2]
    for override in CONFIG_OVERRIDES:
        assert ["-c", override] == record["argv"][record["argv"].index(override) - 1 :][:2]
    assert 'base_url="https://proxy.example/v1"' in " ".join(record["argv"])
    assert record["codex_env"] == ["CODEX_HOME"]
    assert (seat_dir / "transcripts" / "rollout-fake-thread.jsonl").exists()


async def run_with_codex_first_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, steps: list[dict[str, Any]]
) -> SimulationResult:
    """The first seat under the Codex harness on the fake server, the second under pydantic-ai."""
    write_script(tmp_path=tmp_path, monkeypatch=monkeypatch, steps=steps)

    def fake_session() -> CodexSeatSession:
        return CodexSeatSession(launch_command=FAKE_SERVER)

    return await run_mixed_harness_simulation(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(
                round_count=ROUND_COUNT, max_round_duration_seconds=45, model_overrides={}
            )
        ),
        scripts={SECOND_AGENT_ID: speak_then_idle(text="from-second") * ROUND_COUNT},
        session_seats={
            FIRST_AGENT_ID: SessionSeat(
                harness_name=CODEX_HARNESS_NAME, session_factory=fake_session
            )
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def of_first_agent(result: SimulationResult) -> list[Any]:
    return [event for event in result.events if getattr(event, "agent_id", None) == FIRST_AGENT_ID]


async def test_a_codex_seat_plays_a_whole_run_and_logs_what_a_pydantic_ai_seat_would(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_with_codex_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=speak_then_idle_steps(text="from-first") * ROUND_COUNT,
    )

    assert result.of_type(event_type=SimulationEnded), "the run did not finish"
    harness_by_agent = {
        event.agent_id: event.harness for event in result.of_type(event_type=AgentRegistered)
    }
    assert harness_by_agent == {
        FIRST_AGENT_ID: CODEX_HARNESS_NAME,
        SECOND_AGENT_ID: PYDANTIC_AI_HARNESS_NAME,
    }
    sent_by_first = [
        event.message.text
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id == FIRST_AGENT_ID
    ]
    assert sent_by_first == ["from-first"] * ROUND_COUNT
    first = of_first_agent(result=result)
    parented = {
        call.call_id
        for event in first
        if isinstance(event, LLMResponseReceived)
        for call in event.tool_calls
    }
    invoked = {event.call_id for event in first if isinstance(event, ToolCallInvoked)}
    returned = {event.call_id for event in first if isinstance(event, ToolResultReceived)}
    assert invoked and invoked <= parented
    assert returned <= invoked
    assert [event.session_id for event in first if isinstance(event, HarnessSessionBound)] == [
        "fake-thread"
    ]
    assert not [event for event in first if isinstance(event, AgentRunCycleFailed)]


async def test_a_wait_issued_beside_another_call_is_refused_without_parking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex runs a response's calls one after another, so a parked wait would hold the next."""
    result = await run_with_codex_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[
            {
                "parallel": [
                    {"tool": "read_notifications", "arguments": {}},
                    {"tool": "list_channels", "arguments": {}},
                ]
            },
            {"say": "saw the refusal"},
            *speak_then_idle_steps(text="from-first") * ROUND_COUNT,
        ],
    )

    first_wait_result = next(
        event
        for event in of_first_agent(result=result)
        if isinstance(event, ToolResultReceived) and event.tool_name == "read_notifications"
    )
    assert "cannot be issued in parallel" in first_wait_result.result
    assert result.of_type(event_type=SimulationEnded)


async def test_a_dropped_stream_bad_arguments_and_a_compaction_mid_turn_are_logged_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retried request opens its own response, so a wait issued alone is not refused."""
    result = await run_with_codex_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[
            {"dropped_call": {"tool": "list_channels", "arguments": {}}},
            {"bad_arguments": "send_message"},
            {"compaction": True},
            *speak_then_idle_steps(text="from-first") * ROUND_COUNT,
        ],
    )

    first = of_first_agent(result=result)
    assert not [event for event in first if isinstance(event, AgentRunCycleFailed)]
    responses = [event for event in first if isinstance(event, LLMResponseReceived)]
    calls_per_response = [[call.tool_name for call in event.tool_calls] for event in responses]
    assert calls_per_response[:3] == [["list_channels"], ["send_message"], []]
    assert responses[0].usage.input_tokens == 0, "the dropped request reported no usage"
    bad_call = responses[1].tool_calls[0]
    assert bad_call.arguments == {UNPARSED_ARGUMENTS_KEY: "{not json"}
    assert [event for event in first if isinstance(event, ContextCompacted)]
    waits = [
        event
        for event in first
        if isinstance(event, ToolResultReceived) and event.tool_name == "read_notifications"
    ]
    assert waits
    assert not [event for event in waits if "cannot be issued in parallel" in event.result]
    assert result.of_type(event_type=SimulationEnded)


async def test_a_server_that_dies_stops_the_seat_rather_than_continue_unlogged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A thread continued in a new app server sends no raw events, so it is not continued."""
    result = await run_with_codex_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[{"exit": True}],
    )

    first = of_first_agent(result=result)
    failures = [event for event in first if isinstance(event, AgentRunCycleFailed)]
    assert [event.error_type for event in failures] == [
        "AppServerExited",
        "CodexThreadNotResumable",
    ]
    assert "exited with code 3" in failures[0].message
    codex_home = tmp_path / "harness" / FIRST_AGENT_ID / HARNESS_STATE_DIR_NAME / "codex_home"
    record = json.loads((codex_home / fake_codex_app_server.RECORD_FILE_NAME).read_text())
    assert "thread/resume" not in [r["method"] for r in record["requests"]]
    assert not [event for event in first if isinstance(event, ToolCallInvoked)]
    assert result.of_type(event_type=SimulationEnded), "the other seat did not finish the run"


async def test_a_notification_that_cannot_be_read_ends_the_session_instead_of_hanging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_with_codex_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[{"malformed": True}],
    )

    failures = [
        event for event in of_first_agent(result=result) if isinstance(event, AgentRunCycleFailed)
    ]
    assert [event.error_type for event in failures] == [
        "AppServerExited",
        "CodexThreadNotResumable",
    ]
    assert "could not be handled" in failures[0].message
    assert result.of_type(event_type=SimulationEnded)


async def test_a_reader_that_died_between_turns_fails_the_next_request_instead_of_hanging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_script(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        steps=[{"say": "done", "then_garbage": True}],
    )
    session = CodexSeatSession(launch_command=FAKE_SERVER)
    await session.connect(
        options=SeatOptions(
            model="gpt-5.4",
            system_prompt="You observe.",
            tools=(),
            max_output_tokens=2048,
            seat_dir=tmp_path / "seat",
            resume_session_id=None,
        )
    )
    await session.send(prompt="Begin.")
    items = [item async for item in session.items()]
    assert isinstance(items[-1], CycleEnded)

    with pytest.raises(AppServerExited, match="could not be handled"):
        await session.send(prompt="Continue.")
    await session.close()


async def test_a_relative_seat_directory_is_resolved_before_the_server_starts_in_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--runs-dir ./runs`` gives a relative run directory; the server's cwd is the workspace."""
    write_script(tmp_path=tmp_path, monkeypatch=monkeypatch, steps=[{"say": "done"}])
    monkeypatch.chdir(tmp_path)
    session = CodexSeatSession(launch_command=FAKE_SERVER)
    await session.connect(
        options=SeatOptions(
            model="gpt-5.4",
            system_prompt="You observe.",
            tools=(),
            max_output_tokens=2048,
            seat_dir=Path("runs") / "harness" / "field_observer",
            resume_session_id=None,
        )
    )
    await session.send(prompt="Begin.")
    items = [item async for item in session.items()]
    await session.close()

    assert isinstance(items[-1], CycleEnded)
    seat_dir = tmp_path / "runs" / "harness" / "field_observer"
    assert (seat_dir / "transcripts" / "rollout-fake-thread.jsonl").exists()


def test_the_codex_harness_drives_openai_seats_only() -> None:
    remedies = CodexAppServerHarness.preflight(
        seats=(
            HarnessSeat(name="field_observer", model="gpt-5.4", provider=Provider.OPENAI),
            HarnessSeat(name="engineer", model="claude-sonnet-4-6", provider=Provider.ANTHROPIC),
        )
    )

    assert remedies == (
        "run these seats under provider openai; Codex drives OpenAI models only, not anthropic",
    )
