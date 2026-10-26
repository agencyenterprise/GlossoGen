"""What the MCP run-browser tools return for the runs a group can see.

Each tool is called through the server ``_build_mcp_server`` registers, so the
argument names, the result serialization and the ``ValueError`` to ``ToolError``
wrapping are the ones a client meets. The ``RunContext`` has no pool, which is
the no-database path: runs are discovered from the directory built here.
"""

from pathlib import Path
from typing import Any
from uuid import UUID

import orjson
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.types import CallToolResult

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    LLMResponseReceived,
    MessageSent,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.message import SimulationMessage
from glossogen.run_derivation.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.run_file_paths import debug_log_path, evaluation_report_path, event_log_path
from glossogen.server.mcp import browser
from glossogen.server.mcp.browser import _build_mcp_server  # pyright: ignore[reportPrivateUsage]
from glossogen.server.mcp.in_memory_oauth_storage import InMemoryOAuthStorage
from glossogen.server.mcp.oauth_provider import GlossoGenOAuthProvider
from glossogen.server.mcp.run_context import RunContext, set_run_context
from glossogen.server.runs.bundle_router import router as bundle_router
from glossogen.server.runs.manifest_sources import FORK_MANIFEST_FILENAME

ISSUER = "https://example.test/mcp"
GROUP_ID = UUID("44444444-4444-4444-8444-444444444444")
GROUP_SLUG = "team-b"

PARENT = "veyru/1770000001"
FORKED = "veyru/1770000002"
REPLACED = "veyru/1770000003"
OTHER_SCENARIO = "spot_the_difference/1770000004"

EVALUATION = [
    {
        "metric_name": "round_success",
        "score": 0.5,
        "score_unit": "fraction",
        "summary": "half the rounds",
        "per_round": [{"round_number": 1, "value": 1.0, "note": "solved"}],
        "per_agent": [{"agent_id": "alice", "value": 0.0, "note": ""}],
    }
]

USAGE = TokenUsage(
    input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0
)


def _started(run_id: str, provider: str) -> SimulationStarted:
    scenario_name = run_id.split("/", 1)[0]
    return SimulationStarted(
        round_number=0,
        run_id=run_id,
        scenario_name=scenario_name,
        scenario_description="",
        channel_ids=["link", "ops"],
        provider=provider,
        scenario_config={},
    )


def _registered(agent_id: str, model: str, provider: str) -> AgentRegistered:
    return AgentRegistered(
        round_number=0,
        agent_id=agent_id,
        role_name=agent_id.title(),
        model=model,
        provider=provider,
        system_prompt=f"You are {agent_id}.",
        channel_ids=["link", "ops"],
        tool_names=["send_message"],
        model_settings=AgentModelSettings(max_tokens=1024),
    )


def _sent(message_id: str, agent_id: str, channel_id: str, round_number: int) -> MessageSent:
    return MessageSent(
        round_number=round_number,
        message=SimulationMessage(
            message_id=message_id,
            channel_id=channel_id,
            sender_agent_id=agent_id,
            sender_display_name=agent_id.title(),
            text=f"{agent_id} on {channel_id} in round {round_number}",
            timestamp=EventBase(round_number=round_number).timestamp,
            round_number=round_number,
        ),
        token_count=5,
    )


def _turn(agent_id: str, call_id: str) -> list[EventBase]:
    """One LLM response with thinking and a tool call, and the call's result."""
    return [
        ToolCallInvoked(
            round_number=1,
            agent_id=agent_id,
            call_id=call_id,
            tool_name="send_message",
            arguments={"channel_id": "link"},
        ),
        ToolResultReceived(
            round_number=1,
            agent_id=agent_id,
            tool_name="send_message",
            call_id=call_id,
            arguments={"channel_id": "link"},
            result="sent",
        ),
        LLMResponseReceived(
            round_number=1,
            agent_id=agent_id,
            thinking=f"{agent_id} is thinking",
            text=None,
            tool_calls=[],
            stop_reason=StopReason.TOOL_USE,
            usage=USAGE,
        ),
    ]


def _ended() -> SimulationEnded:
    return SimulationEnded(
        round_number=2,
        reason=RunStatus.SCENARIO_COMPLETE,
        total_messages=4,
        total_cost_usd=0.25,
    )


def _write_run(runs_dir: Path, run_id: str, events: list[EventBase], labels: list[str]) -> Path:
    scenario_name, run_dir_name = run_id.split("/", 1)
    run_dir = runs_dir / scenario_name / run_dir_name
    run_dir.mkdir(parents=True)
    lines = [event.model_dump_json().encode() for event in events]
    event_log_path(run_dir=run_dir, scenario_name=scenario_name).write_bytes(
        b"\n".join(lines) + b"\n"
    )
    (run_dir / "labels.json").write_bytes(orjson.dumps(labels))
    return run_dir


def _two_agent_run(run_id: str) -> list[EventBase]:
    """Alice on opus and Bob on gpt, a message each on two channels, one finished run."""
    return [
        _started(run_id=run_id, provider="anthropic"),
        _registered(agent_id="alice", model="claude-opus-4-1", provider="anthropic"),
        _registered(agent_id="bob", model="gpt-5", provider="openai"),
        _sent(message_id="m1", agent_id="alice", channel_id="link", round_number=1),
        _sent(message_id="m2", agent_id="bob", channel_id="link", round_number=1),
        _sent(message_id="m3", agent_id="alice", channel_id="ops", round_number=2),
        _sent(message_id="m4", agent_id="bob", channel_id="ops", round_number=2),
        *_turn(agent_id="alice", call_id="c1"),
        *_turn(agent_id="bob", call_id="c2"),
        _ended(),
    ]


@pytest.fixture(name="runs_dir")
def runs_dir_fixture(tmp_path: Path) -> Path:
    """A parent run, a fork and a replace-agent run of it, and a run of another scenario."""
    runs_dir = tmp_path / "runs"
    parent_dir = _write_run(
        runs_dir=runs_dir,
        run_id=PARENT,
        events=_two_agent_run(run_id=PARENT),
        labels=["baseline", "budget=800"],
    )
    evaluation_report_path(run_dir=parent_dir, scenario_name="veyru").write_bytes(
        orjson.dumps(
            {"simulation_id": PARENT, "scenario_name": "veyru", "measurements": EVALUATION}
        )
    )
    debug_log_path(run_dir=parent_dir, scenario_name="veyru").write_bytes(
        b"\n".join(
            orjson.dumps(
                {
                    "timestamp": f"2026-10-26T00:00:{i:02d}",
                    "logger": "glossogen",
                    "level": "INFO",
                    "message": f"line {i}",
                }
            )
            for i in range(120)
        )
    )

    forked_dir = _write_run(
        runs_dir=runs_dir,
        run_id=FORKED,
        events=[_started(run_id=FORKED, provider="anthropic")],
        labels=["baseline"],
    )
    (forked_dir / FORK_MANIFEST_FILENAME).write_bytes(
        orjson.dumps({"source_run_id": PARENT, "target_message_id": "m2", "forked_at": 1.7e9})
    )

    replaced_dir = _write_run(
        runs_dir=runs_dir,
        run_id=REPLACED,
        events=[_started(run_id=REPLACED, provider="anthropic"), _ended()],
        labels=["budget=800"],
    )
    (replaced_dir / REPLACE_MANIFEST_FILENAME).write_bytes(
        ReplaceManifest(
            source_run_id=PARENT,
            source_run_dir=str(parent_dir),
            round_start=2,
            rounds_after_swap=1,
            target_event_id="e1",
            replaced_agent_id="bob",
            replacement_model="claude-haiku-4-5",
            replacement_provider="anthropic",
            channels_with_visible_history=["link"],
            blocked_tool_call_channels=[],
            channel_history_floors={},
            history_floor_round=None,
            replaced_at=1.7e9,
        )
        .model_dump_json()
        .encode()
    )

    _write_run(
        runs_dir=runs_dir,
        run_id=OTHER_SCENARIO,
        events=[
            _started(run_id=OTHER_SCENARIO, provider="openai"),
            _registered(agent_id="carol", model="gpt-5-mini", provider="openai"),
            _ended(),
        ],
        labels=[],
    )
    return runs_dir


@pytest.fixture(name="server")
def server_fixture() -> MCPServer:
    """The run-browser server, with every tool registered as in production."""
    provider = GlossoGenOAuthProvider(
        storage=InMemoryOAuthStorage(),
        get_local_group_id=lambda: GROUP_ID,
        identity_provider=None,
        resource_server_url=ISSUER,
    )
    return _build_mcp_server(oauth_provider=provider, issuer_url=ISSUER)


@pytest.fixture(autouse=True)
def no_launches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that reaches the simulation launcher without replacing it first."""

    def refuse_launch(**kwargs: Any) -> None:
        pytest.fail(f"start_run reached launch_simulation with {kwargs}")

    monkeypatch.setattr(browser, "launch_simulation", refuse_launch)


async def _call(
    server: MCPServer, runs_dir: Path, tool: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Call ``tool`` the way an authenticated request would, and return its JSON result."""
    set_run_context(
        RunContext(runs_dir=runs_dir, pool=None, group_id=GROUP_ID, group_slug=GROUP_SLUG)
    )
    result = await server.call_tool(name=tool, arguments=arguments)
    assert isinstance(result, CallToolResult)
    structured: dict[str, Any] | None = result.structured_content
    assert structured is not None
    return structured


async def _rejection(
    server: MCPServer, runs_dir: Path, tool: str, arguments: dict[str, Any]
) -> str:
    """Call ``tool`` expecting a rejection the client can read, and return its text."""
    with pytest.raises(ToolError) as caught:
        await _call(server=server, runs_dir=runs_dir, tool=tool, arguments=arguments)
    assert not isinstance(caught.value, UnexpectedToolError)
    return str(caught.value)


def _run_ids(result: dict[str, Any]) -> list[str]:
    return [run["run_id"] for run in result["runs"]]


async def test_list_runs_returns_every_run_newest_first(server: MCPServer, runs_dir: Path) -> None:
    result = await _call(server=server, runs_dir=runs_dir, tool="list_runs", arguments={})

    assert _run_ids(result=result) == [OTHER_SCENARIO, REPLACED, FORKED, PARENT]
    assert result["total"] == 4
    by_id = {run["run_id"]: run for run in result["runs"]}
    assert by_id[PARENT]["labels"] == ["baseline", "budget=800"]
    assert by_id[PARENT]["parent_run_id"] is None
    assert by_id[FORKED]["is_forked"] is True
    assert by_id[FORKED]["parent_run_id"] == PARENT
    assert by_id[REPLACED]["is_forked"] is False
    assert by_id[REPLACED]["parent_run_id"] == PARENT


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        pytest.param({"scenario": "VEYRU"}, [REPLACED, FORKED, PARENT], id="scenario-substring"),
        pytest.param({"model": "GPT-5-MINI"}, [OTHER_SCENARIO], id="model-substring"),
        pytest.param({"is_forked": True}, [FORKED], id="forked"),
        # `is_forked` means forked at a message: a replace-agent run is not one.
        pytest.param({"is_forked": False}, [OTHER_SCENARIO, REPLACED, PARENT], id="not-forked"),
        pytest.param({"status": "STARTING"}, [FORKED], id="status"),
        pytest.param({"labels": ["baseline"]}, [FORKED, PARENT], id="one-label"),
        pytest.param({"labels": ["baseline", "budget=800"]}, [PARENT], id="labels-are-anded"),
        pytest.param({"scenario": "veyru", "labels": ["budget=800"]}, [REPLACED, PARENT], id="and"),
    ],
)
async def test_list_runs_filters(
    server: MCPServer, runs_dir: Path, arguments: dict[str, Any], expected: list[str]
) -> None:
    result = await _call(server=server, runs_dir=runs_dir, tool="list_runs", arguments=arguments)

    assert _run_ids(result=result) == expected
    assert result["total"] == len(expected)


async def test_list_runs_pages_after_filtering(server: MCPServer, runs_dir: Path) -> None:
    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="list_runs",
        arguments={"scenario": "veyru", "offset": 1, "limit": 1},
    )

    assert _run_ids(result=result) == [FORKED]
    assert result["total"] == 3
    assert (result["offset"], result["limit"]) == (1, 1)


async def test_a_unique_prefix_names_the_run(server: MCPServer, runs_dir: Path) -> None:
    result = await _call(
        server=server, runs_dir=runs_dir, tool="get_run_metadata", arguments={"run_id": "spot"}
    )

    assert result["run_id"] == OTHER_SCENARIO


@pytest.mark.parametrize(
    ("run_id", "reason"),
    [
        pytest.param("veyru/17", "Ambiguous prefix 'veyru/17' matches 3 runs", id="ambiguous"),
        pytest.param("veyru/9", "No run found matching prefix 'veyru/9'", id="unknown"),
    ],
)
@pytest.mark.parametrize(
    "tool",
    [
        "get_run_metadata",
        "get_run",
        "list_derived_runs",
        "export_run_artifacts",
        "export_agent_atif",
        "export_agent_thread",
    ],
)
async def test_a_prefix_that_names_no_single_run_is_rejected_with_its_reason(
    server: MCPServer, runs_dir: Path, tool: str, run_id: str, reason: str
) -> None:
    arguments: dict[str, Any] = {"run_id": run_id}
    if tool in ("export_agent_atif", "export_agent_thread"):
        arguments["agent_id"] = "alice"

    text = await _rejection(server=server, runs_dir=runs_dir, tool=tool, arguments=arguments)

    assert reason in text


async def test_a_full_run_id_names_its_run_beside_a_same_second_sibling(
    server: MCPServer, runs_dir: Path
) -> None:
    sibling = f"{PARENT}_2"
    _write_run(
        runs_dir=runs_dir,
        run_id=sibling,
        events=[_started(run_id=sibling, provider="anthropic"), _ended()],
        labels=[],
    )

    result = await _call(
        server=server, runs_dir=runs_dir, tool="get_run_metadata", arguments={"run_id": PARENT}
    )

    assert result["run_id"] == PARENT


async def test_an_ambiguous_prefix_names_the_runs_it_matched(
    server: MCPServer, runs_dir: Path
) -> None:
    text = await _rejection(
        server=server, runs_dir=runs_dir, tool="get_run_metadata", arguments={"run_id": "veyru/"}
    )

    for run_id in (PARENT, FORKED, REPLACED):
        assert run_id in text


async def test_run_metadata_carries_the_evaluation_and_the_roster(
    server: MCPServer, runs_dir: Path
) -> None:
    result = await _call(
        server=server, runs_dir=runs_dir, tool="get_run_metadata", arguments={"run_id": PARENT}
    )

    assert result["status"] == RunStatus.SCENARIO_COMPLETE.value
    assert [agent["agent_id"] for agent in result["agent_models"]] == ["alice", "bob"]
    assert result["evaluation"] == EVALUATION


async def test_run_metadata_without_a_readable_report_has_no_evaluation(
    server: MCPServer, runs_dir: Path
) -> None:
    evaluation_report_path(run_dir=runs_dir / REPLACED, scenario_name="veyru").write_bytes(
        b"{not json"
    )

    unreadable = await _call(
        server=server, runs_dir=runs_dir, tool="get_run_metadata", arguments={"run_id": REPLACED}
    )
    absent = await _call(
        server=server, runs_dir=runs_dir, tool="get_run_metadata", arguments={"run_id": FORKED}
    )

    assert unreadable["evaluation"] is None
    assert absent["evaluation"] is None


async def test_run_metadata_carries_the_provenance_of_a_derived_run(
    server: MCPServer, runs_dir: Path
) -> None:
    forked = await _call(
        server=server, runs_dir=runs_dir, tool="get_run_metadata", arguments={"run_id": FORKED}
    )
    replaced = await _call(
        server=server, runs_dir=runs_dir, tool="get_run_metadata", arguments={"run_id": REPLACED}
    )

    assert forked["parent_run_id"] == PARENT
    assert forked["fork_source"]["target_message_id"] == "m2"
    assert forked["replace_agent_source"] is None
    assert replaced["parent_run_id"] == PARENT
    assert replaced["fork_source"] is None
    assert replaced["replace_agent_source"]["replaced_agent_id"] == "bob"
    assert replaced["replace_agent_source"]["replacement_model"] == "claude-haiku-4-5"


async def test_list_derived_runs_lists_the_children_of_the_parent_only(
    server: MCPServer, runs_dir: Path
) -> None:
    result = await _call(
        server=server, runs_dir=runs_dir, tool="list_derived_runs", arguments={"run_id": PARENT}
    )
    childless = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="list_derived_runs",
        arguments={"run_id": OTHER_SCENARIO},
    )

    assert result["parent_run_id"] == PARENT
    assert [child["run_id"] for child in result["derived_runs"]] == [REPLACED]
    assert result["derived_runs"][0]["derivation_type"] == "replace_agent"
    assert result["derived_runs"][0]["replaced_agent_id"] == "bob"
    assert result["total"] == 1
    assert childless["derived_runs"] == []


async def test_get_run_leaves_out_every_optional_section_by_default(
    server: MCPServer, runs_dir: Path
) -> None:
    result = await _call(
        server=server, runs_dir=runs_dir, tool="get_run", arguments={"run_id": PARENT}
    )

    assert [message["message_id"] for message in result["messages"]] == ["m1", "m2", "m3", "m4"]
    assert result["total_messages"] == 4
    assert result["agents"] is None
    assert result["reasoning"] is None
    assert result["tool_use"] is None
    assert result["debug_logs"] is None


async def test_get_run_filtered_to_an_agent_filters_every_section(
    server: MCPServer, runs_dir: Path
) -> None:
    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="get_run",
        arguments={
            "run_id": PARENT,
            "agent_id": "bob",
            "with_reasoning": True,
            "with_tool_use": True,
            "with_system_prompts": True,
        },
    )

    assert [message["message_id"] for message in result["messages"]] == ["m2", "m4"]
    assert [agent["system_prompt"] for agent in result["agents"]] == ["You are bob."]
    assert [entry["text"] for entry in result["reasoning"]] == ["bob is thinking"]
    assert [(call["tool_name"], call["result"]) for call in result["tool_use"]] == [
        ("send_message", "sent")
    ]
    assert {call["sender_agent_id"] for call in result["tool_use"]} == {"bob"}


async def test_get_run_pages_the_messages_of_one_channel(server: MCPServer, runs_dir: Path) -> None:
    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="get_run",
        arguments={"run_id": PARENT, "channel_id": "ops", "message_offset": 1, "message_limit": 5},
    )

    assert [message["message_id"] for message in result["messages"]] == ["m4"]
    assert result["total_messages"] == 2


async def test_get_run_filters_by_agent_and_channel_together(
    server: MCPServer, runs_dir: Path
) -> None:
    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="get_run",
        arguments={"run_id": PARENT, "agent_id": "bob", "channel_id": "ops"},
    )

    assert [message["message_id"] for message in result["messages"]] == ["m4"]
    assert result["total_messages"] == 1


async def test_get_run_keeps_the_first_50_reasoning_and_tool_use_entries(
    server: MCPServer, runs_dir: Path
) -> None:
    run_id = "veyru/1770000005"
    turns = [event for i in range(60) for event in _turn(agent_id="alice", call_id=f"c{i}")]
    _write_run(
        runs_dir=runs_dir,
        run_id=run_id,
        events=[
            _started(run_id=run_id, provider="anthropic"),
            _registered(agent_id="alice", model="claude-opus-4-1", provider="anthropic"),
            *turns,
            _ended(),
        ],
        labels=[],
    )

    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="get_run",
        arguments={"run_id": run_id, "with_reasoning": True, "with_tool_use": True},
    )

    assert len(result["reasoning"]) == 50
    assert [call["message_id"].rsplit("-", 1)[1] for call in result["tool_use"]] == [
        f"c{i}" for i in range(50)
    ]


async def test_get_run_returns_the_latest_debug_log_lines(
    server: MCPServer, runs_dir: Path
) -> None:
    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="get_run",
        arguments={"run_id": PARENT, "with_debug_logs": True},
    )

    messages = [entry["message"] for entry in result["debug_logs"]]
    assert messages == [f"line {i}" for i in range(20, 120)]


async def test_export_run_artifacts_points_at_the_bundle_route_of_the_group(
    server: MCPServer, runs_dir: Path
) -> None:
    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="export_run_artifacts",
        arguments={"run_id": PARENT},
    )

    assert result == {
        "run_id": PARENT,
        "scenario_name": "veyru",
        "download_url": bundle_router.url_path_for(
            "export_run_bundle",
            group_slug=GROUP_SLUG,
            scenario="veyru",
            run_dir_name="1770000001",
        ),
        "filename": "veyru_1770000001_bundle.tar.gz",
    }


async def test_export_agent_thread_rejects_an_unknown_output_format(
    server: MCPServer, runs_dir: Path
) -> None:
    text = await _rejection(
        server=server,
        runs_dir=runs_dir,
        tool="export_agent_thread",
        arguments={"run_id": PARENT, "agent_id": "alice", "output_format": "gemini"},
    )

    assert "output_format must be 'anthropic' or 'openai', got 'gemini'" in text


@pytest.mark.parametrize(
    ("agent_id", "output_format", "expected_format"),
    [
        pytest.param("alice", None, "anthropic_messages", id="anthropic-agent-default"),
        pytest.param("bob", None, "openai_chat", id="openai-agent-default"),
        pytest.param("alice", "openai", "openai_chat", id="openai"),
        pytest.param("bob", "anthropic", "anthropic_messages", id="anthropic"),
    ],
)
async def test_export_agent_thread_exports_in_the_format_asked_for(
    server: MCPServer,
    runs_dir: Path,
    agent_id: str,
    output_format: str | None,
    expected_format: str,
) -> None:
    arguments: dict[str, Any] = {"run_id": PARENT, "agent_id": agent_id}
    if output_format is not None:
        arguments["output_format"] = output_format

    result = await _call(
        server=server, runs_dir=runs_dir, tool="export_agent_thread", arguments=arguments
    )

    assert result["meta"]["run_id"] == PARENT
    assert result["meta"]["agent_id"] == agent_id
    assert result["meta"]["format"] == expected_format


async def test_export_agent_atif_exports_the_agent_asked_for(
    server: MCPServer, runs_dir: Path
) -> None:
    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="export_agent_atif",
        arguments={"run_id": PARENT, "agent_id": "alice"},
    )

    assert [trajectory["trajectory_id"] for trajectory in result["trajectories"]] == [
        f"{PARENT}/alice"
    ]


async def test_a_listed_preset_loads(server: MCPServer, runs_dir: Path) -> None:
    schema = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="get_knobs_schema",
        arguments={"scenario_name": "veyru"},
    )
    preset_name = schema["knobs_files"][0]

    preset = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="get_knobs_preset",
        arguments={"scenario_name": "veyru", "knobs_file": preset_name},
    )

    assert preset["knobs_file"] == preset_name
    assert preset["knobs"]
    assert preset["knobs"].keys() <= schema["knobs_schema"]["properties"].keys()


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        pytest.param("get_knobs_schema", {}, id="schema"),
        pytest.param("get_knobs_preset", {"knobs_file": "baseline"}, id="preset"),
        pytest.param("start_run", {"model": "gpt-5", "provider": "openai"}, id="start"),
    ],
)
async def test_an_unknown_scenario_is_rejected_with_its_reason(
    server: MCPServer, runs_dir: Path, tool: str, arguments: dict[str, Any]
) -> None:
    text = await _rejection(
        server=server,
        runs_dir=runs_dir,
        tool=tool,
        arguments={"scenario_name": "no_such_scenario", **arguments},
    )

    assert "Unknown scenario: 'no_such_scenario'" in text


async def test_start_run_launches_into_the_runs_dir_and_group_of_the_request(
    server: MCPServer, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launches: list[dict[str, Any]] = []

    def record_launch(**kwargs: Any) -> None:
        launches.append(kwargs)

    monkeypatch.setattr(browser, "launch_simulation", record_launch)

    result = await _call(
        server=server,
        runs_dir=runs_dir,
        tool="start_run",
        arguments={
            "scenario_name": "veyru",
            "model": "gpt-5",
            "provider": "openai",
            "knobs": {"round_count": 3},
        },
    )

    assert result["status"] == "started"
    assert len(launches) == 1
    assert launches[0]["runs_dir"] == runs_dir
    assert launches[0]["group_slug"] == GROUP_SLUG
    assert launches[0]["knobs"] == {"round_count": 3}
    assert (launches[0]["model"], launches[0]["provider"]) == ("gpt-5", "openai")
