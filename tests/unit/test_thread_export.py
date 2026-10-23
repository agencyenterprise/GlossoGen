"""Exporting an agent's thread as an Anthropic Messages or OpenAI Chat request body.

The serializer tests hand it a pydantic-ai history and compare the dumped body
with the wire format each provider accepts. The orchestration tests write a
small event log to disk and export from it, the way the CLI, the MCP tool and
the REST endpoint do.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.mcp_responses import SendReceipt, SendStatus
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.run_file_paths import event_log_path
from glossogen.thread_export.export_agent_thread import export_agent_thread_from_run_dir
from glossogen.thread_export.provider_thread_serializer import (
    to_anthropic_request,
    to_openai_request,
)
from glossogen.thread_export.thread_export_models import (
    AnthropicRequest,
    AnthropicToolUseBlock,
    OpenAIAssistantMessage,
    OpenAIRequest,
    OpenAISystemMessage,
)

_SEND_ARGS = {"channel_id": "link", "text": "hi"}
_SEND_ARGS_JSON = '{"channel_id":"link","text":"hi"}'
_TOOL_CALL_TEXT = f"[tool_call send_message({_SEND_ARGS_JSON})]"
_TOOL_RESULT_TEXT = '[tool_result send_message]\n{"status": "sent"}'


def _history() -> list[ModelMessage]:
    """A two-turn thread: briefing, a reply with a tool call, its result, a nudge, a reply.

    The tool result and the nudge arrive as two consecutive requests, the shape
    a runner produces when it continues the agent after a tool turn.
    """
    return [
        ModelRequest(parts=[SystemPromptPart(content="sys"), UserPromptPart(content="brief")]),
        ModelResponse(
            parts=[
                ThinkingPart(content="plan"),
                TextPart(content="on it"),
                ToolCallPart(tool_name="send_message", args=_SEND_ARGS, tool_call_id="c1"),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="send_message", content={"status": "sent"}, tool_call_id="c1"
                )
            ]
        ),
        ModelRequest(parts=[UserPromptPart(content="continue")]),
        ModelResponse(parts=[TextPart(content="done")]),
    ]


def _anthropic(
    messages: list[ModelMessage], include_thinking: bool, flatten_tools: bool
) -> dict[str, Any]:
    """The Anthropic body for ``messages``, dumped as it would be sent."""
    return to_anthropic_request(
        messages=messages,
        model="claude-x",
        include_thinking=include_thinking,
        flatten_tools=flatten_tools,
    ).model_dump(mode="json")


def _openai(
    messages: list[ModelMessage], include_thinking: bool, flatten_tools: bool
) -> dict[str, Any]:
    """The OpenAI body for ``messages``, dumped as it would be sent."""
    return to_openai_request(
        messages=messages,
        model="gpt-x",
        include_thinking=include_thinking,
        flatten_tools=flatten_tools,
    ).model_dump(mode="json")


def _text(text: str) -> dict[str, str]:
    """An Anthropic text block."""
    return {"type": "text", "text": text}


def test_anthropic_body_uses_native_tool_blocks_and_alternates_roles() -> None:
    assert _anthropic(messages=_history(), include_thinking=False, flatten_tools=False) == {
        "model": "claude-x",
        "system": "sys",
        "messages": [
            {"role": "user", "content": [_text(text="brief")]},
            {
                "role": "assistant",
                "content": [
                    _text(text="on it"),
                    {"type": "tool_use", "id": "c1", "name": "send_message", "input": _SEND_ARGS},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "c1", "content": '{"status": "sent"}'},
                    _text(text="continue"),
                ],
            },
            {"role": "assistant", "content": [_text(text="done")]},
        ],
    }


def test_anthropic_body_with_thinking_and_flattened_tools_is_text_only() -> None:
    body = _anthropic(messages=_history(), include_thinking=True, flatten_tools=True)
    assert body["messages"] == [
        {"role": "user", "content": [_text(text="brief")]},
        {
            "role": "assistant",
            "content": [_text(text="plan"), _text(text="on it"), _text(text=_TOOL_CALL_TEXT)],
        },
        {"role": "user", "content": [_text(text=_TOOL_RESULT_TEXT), _text(text="continue")]},
        {"role": "assistant", "content": [_text(text="done")]},
    ]


def test_openai_body_uses_tool_calls_and_tool_messages() -> None:
    assert _openai(messages=_history(), include_thinking=False, flatten_tools=False) == {
        "model": "gpt-x",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "brief"},
            {
                "role": "assistant",
                "content": "on it",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "send_message", "arguments": _SEND_ARGS_JSON},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"status": "sent"}'},
            {"role": "user", "content": "continue"},
            {"role": "assistant", "content": "done"},
        ],
    }


def test_openai_body_with_thinking_and_flattened_tools_is_text_only() -> None:
    body = _openai(messages=_history(), include_thinking=True, flatten_tools=True)
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "brief"},
        {"role": "assistant", "content": f"plan\non it\n{_TOOL_CALL_TEXT}"},
        {"role": "user", "content": _TOOL_RESULT_TEXT},
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "done"},
    ]


def test_openai_tool_call_only_turn_carries_no_content_key() -> None:
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="brief")]),
        ModelResponse(
            parts=[ToolCallPart(tool_name="send_message", args=_SEND_ARGS, tool_call_id="c1")]
        ),
    ]
    [_, assistant] = _openai(messages=history, include_thinking=False, flatten_tools=False)[
        "messages"
    ]
    assert assistant == {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "send_message", "arguments": _SEND_ARGS_JSON},
            }
        ],
    }


def _thinking_only_history() -> list[ModelMessage]:
    """A thread whose middle response holds nothing but thinking."""
    return [
        ModelRequest(parts=[UserPromptPart(content="brief")]),
        ModelResponse(parts=[ThinkingPart(content="plan")]),
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]


def test_a_response_left_empty_without_its_thinking_is_dropped() -> None:
    anthropic = _anthropic(
        messages=_thinking_only_history(), include_thinking=False, flatten_tools=False
    )
    assert anthropic["messages"] == [
        {"role": "user", "content": [_text(text="brief"), _text(text="continue")]}
    ]
    openai = _openai(messages=_thinking_only_history(), include_thinking=False, flatten_tools=False)
    assert openai["messages"] == [
        {"role": "user", "content": "brief"},
        {"role": "user", "content": "continue"},
    ]


def test_system_parts_are_joined_and_an_absent_system_prompt_adds_nothing() -> None:
    with_two: list[ModelMessage] = [
        ModelRequest(parts=[SystemPromptPart(content="one"), SystemPromptPart(content="two")]),
        ModelRequest(parts=[UserPromptPart(content="brief")]),
    ]
    assert _anthropic(messages=with_two, include_thinking=False, flatten_tools=False)["system"] == (
        "one\n\ntwo"
    )
    assert _openai(messages=with_two, include_thinking=False, flatten_tools=False)["messages"][
        0
    ] == {"role": "system", "content": "one\n\ntwo"}

    without: list[ModelMessage] = [ModelRequest(parts=[UserPromptPart(content="brief")])]
    assert _anthropic(messages=without, include_thinking=False, flatten_tools=False)["system"] == ""
    assert _openai(messages=without, include_thinking=False, flatten_tools=False)["messages"] == [
        {"role": "user", "content": "brief"}
    ]


_SCENARIO = "smoke"
_SEAT = "seat"


def _usage() -> TokenUsage:
    """A minimal token usage record."""
    return TokenUsage(
        input_tokens=1,
        output_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def _registered(agent_id: str, model: str, provider: str) -> AgentRegistered:
    """An ``AgentRegistered`` event for one seat."""
    return AgentRegistered(
        round_number=0,
        agent_id=agent_id,
        role_name="worker",
        system_prompt=f"you are {agent_id} on {model}",
        channel_ids=["link"],
        tool_names=["send_message"],
        model=model,
        provider=provider,
        model_settings=AgentModelSettings(max_tokens=1024),
    )


def _turn(round_number: int, text: str) -> list[SimulationEvent]:
    """One turn of the seat in ``round_number``: a send on the link and its result."""
    call = ToolCallRequest(
        call_id=f"c-{round_number}",
        tool_name="send_message",
        arguments={"channel_id": "link", "text": text},
    )
    return [
        ToolCallInvoked(
            round_number=round_number,
            agent_id=_SEAT,
            call_id=call.call_id,
            tool_name=call.tool_name,
            arguments=call.arguments,
        ),
        ToolResultReceived(
            round_number=round_number,
            agent_id=_SEAT,
            tool_name=call.tool_name,
            call_id=call.call_id,
            arguments=call.arguments,
            result=SendReceipt(
                status=SendStatus.SENT, message_id=f"m-{round_number}"
            ).model_dump_json(),
        ),
        LLMResponseReceived(
            round_number=round_number,
            agent_id=_SEAT,
            text=None,
            tool_calls=[call],
            stop_reason=StopReason.TOOL_USE,
            usage=_usage(),
        ),
    ]


def _write_run(tmp_path: Path, events: Sequence[SimulationEvent]) -> Path:
    """Write ``events`` as a run's event log, with increasing timestamps, and return the run dir."""
    run_dir = tmp_path / _SCENARIO / "1700000000"
    run_dir.mkdir(parents=True)
    start = datetime(2026, 8, 1, tzinfo=UTC)
    lines: list[str] = []
    for index, event in enumerate(events):
        assert isinstance(event, EventBase)
        stamped = event.model_copy(update={"timestamp": start + timedelta(seconds=index)})
        lines.append(stamped.model_dump_json())
    event_log_path(run_dir=run_dir, scenario_name=_SCENARIO).write_text("\n".join(lines) + "\n")
    return run_dir


def _sent_link_texts(request: AnthropicRequest | OpenAIRequest) -> list[str]:
    """The ``text`` argument of every tool call in the body, in order."""
    texts: list[str] = []
    if isinstance(request, AnthropicRequest):
        for turn in request.messages:
            for block in turn.content:
                if isinstance(block, AnthropicToolUseBlock):
                    texts.append(block.input["text"])
        return texts
    for message in request.messages:
        if isinstance(message, OpenAIAssistantMessage) and message.tool_calls is not None:
            for tool_call in message.tool_calls:
                texts.append(json.loads(tool_call.function.arguments)["text"])
    return texts


def _swapped_run(tmp_path: Path) -> Path:
    """A two-round run where the seat was re-registered under OpenAI and a bystander never acted."""
    return _write_run(
        tmp_path=tmp_path,
        events=[
            SimulationStarted(
                round_number=0,
                run_id=f"{_SCENARIO}/1700000000",
                scenario_name=_SCENARIO,
                scenario_description="",
                channel_ids=["link"],
                scenario_config={"round_count": 2},
                provider="anthropic",
            ),
            _registered(agent_id=_SEAT, model="claude-x", provider="anthropic"),
            _registered(agent_id="bystander", model="claude-x", provider="anthropic"),
            _registered(agent_id=_SEAT, model="gpt-x", provider="openai"),
            *_turn(round_number=1, text="first"),
            *_turn(round_number=2, text="second"),
        ],
    )


async def test_export_defaults_to_the_format_of_the_seats_last_registration(
    tmp_path: Path,
) -> None:
    export = await export_agent_thread_from_run_dir(
        run_dir=_swapped_run(tmp_path=tmp_path),
        scenario_name=_SCENARIO,
        agent_id=_SEAT,
        cutoff_round=None,
        output_format=None,
        include_thinking=False,
        flatten_tools=False,
    )
    assert isinstance(export.request, OpenAIRequest)
    assert export.request.model == "gpt-x"
    system = export.request.messages[0]
    assert isinstance(system, OpenAISystemMessage)
    assert system.content.startswith("you are seat on gpt-x")
    assert export.meta.model_dump(exclude={"exported_at"}) == {
        "run_id": f"{_SCENARIO}/1700000000",
        "agent_id": _SEAT,
        "role_name": "worker",
        "model": "gpt-x",
        "provider": "openai",
        "cutoff_round": None,
        "rounds_covered": "1-2",
        "num_messages": 6,
        "format": "openai_chat",
        "thinking_included": False,
        "tools_flattened": False,
    }
    assert [message.role for message in export.request.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]
    assert _sent_link_texts(request=export.request) == ["first", "second"]


@pytest.mark.parametrize(
    ("cutoff_round", "rounds_covered", "sent"),
    [(2, "1-1", ["first"]), (3, "1-2", ["first", "second"])],
)
async def test_cutoff_round_is_exclusive(
    tmp_path: Path, cutoff_round: int, rounds_covered: str, sent: list[str]
) -> None:
    export = await export_agent_thread_from_run_dir(
        run_dir=_swapped_run(tmp_path=tmp_path),
        scenario_name=_SCENARIO,
        agent_id=_SEAT,
        cutoff_round=cutoff_round,
        output_format="anthropic_messages",
        include_thinking=False,
        flatten_tools=False,
    )
    assert isinstance(export.request, AnthropicRequest)
    assert export.meta.format == "anthropic_messages"
    assert export.meta.rounds_covered == rounds_covered
    assert _sent_link_texts(request=export.request) == sent


async def test_an_agent_the_run_never_registered_is_refused_with_the_ids_it_has(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=r"available agent_ids: bystander, seat"):
        await export_agent_thread_from_run_dir(
            run_dir=_swapped_run(tmp_path=tmp_path),
            scenario_name=_SCENARIO,
            agent_id="ghost",
            cutoff_round=None,
            output_format=None,
            include_thinking=False,
            flatten_tools=False,
        )


@pytest.mark.parametrize(("agent_id", "cutoff_round"), [("bystander", None), (_SEAT, 1)])
async def test_an_empty_history_is_refused(
    tmp_path: Path, agent_id: str, cutoff_round: int | None
) -> None:
    with pytest.raises(ValueError, match="nothing to export"):
        await export_agent_thread_from_run_dir(
            run_dir=_swapped_run(tmp_path=tmp_path),
            scenario_name=_SCENARIO,
            agent_id=agent_id,
            cutoff_round=cutoff_round,
            output_format=None,
            include_thinking=False,
            flatten_tools=False,
        )
