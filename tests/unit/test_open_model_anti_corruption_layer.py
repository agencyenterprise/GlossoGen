"""Tests for ``OpenModelAntiCorruptionLayer`` and ``open_model_capabilities``.

A ``FunctionModel`` makes the tool call and a real pydantic-ai ``Agent`` validates
it, so each test sees the answer the model would get. The main call is
``list_channels(wait_for="any")``, to a tool that takes no arguments. The others
are ``read_notifications`` with an extra ``channel_id``, and arguments that are
not valid JSON. The routing tests check which providers get the layer.
"""

import logging

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import AgentCapability
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition

from glossogen.model_catalog import Provider
from glossogen.runners.open_model_anti_corruption_layer import (
    OpenModelAntiCorruptionLayer,
    open_model_capabilities,
    undeclared_arguments,
)

CALL_ID = "call-1"
CHANNELS = ["link_a", "discussion"]


async def list_channels() -> list[str]:
    """Stands in for the platform's tool of the same name, which takes no arguments."""
    return CHANNELS


async def read_notifications(wait_for: str, timeout_s: float) -> str:
    """Echoes its arguments, so a test sees which ones reached the tool."""
    return f"{wait_for} {timeout_s}"


def calling_once(tool_name: str, args: str) -> FunctionModel:
    """A model that makes one tool call, with ``args`` as an OpenAI-compatible server sends them."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = info
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id=CALL_ID)]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    return FunctionModel(respond)


async def run_agent(
    model: FunctionModel, capabilities: list[AgentCapability[None]]
) -> list[ModelMessage]:
    """Run one agent over both tools and return its whole history."""
    agent = Agent(
        model=model,
        deps_type=type(None),
        tools=[list_channels, read_notifications],
        capabilities=capabilities,
    )
    result = await agent.run(user_prompt="Start.")
    return result.all_messages()


def answer_to_call(messages: list[ModelMessage]) -> ToolReturnPart:
    """What the model was told about its call: the tool's return, or a refusal to retry."""
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_call_id == CALL_ID:
                return part
    raise AssertionError(f"no answer to {CALL_ID}")


def refusal(answer: ToolReturnPart) -> str:
    """The text the model got back for a refused call."""
    assert answer.outcome == "retried"
    return answer.model_response_str()


def layer() -> list[AgentCapability[None]]:
    return [OpenModelAntiCorruptionLayer(agent_id="viewer_a_4")]


async def test_a_tool_that_takes_no_arguments_runs_when_called_with_one() -> None:
    messages = await run_agent(
        model=calling_once(tool_name="list_channels", args='{"wait_for": "any"}'),
        capabilities=layer(),
    )

    answer = answer_to_call(messages=messages)
    assert answer.outcome == "success"
    assert answer.content == CHANNELS


async def test_without_the_layer_the_same_call_is_refused() -> None:
    messages = await run_agent(
        model=calling_once(tool_name="list_channels", args='{"wait_for": "any"}'),
        capabilities=[],
    )

    assert "extra_forbidden" in refusal(answer=answer_to_call(messages=messages))


async def test_the_declared_arguments_reach_the_tool_when_an_undeclared_one_is_dropped() -> None:
    messages = await run_agent(
        model=calling_once(
            tool_name="read_notifications",
            args='{"wait_for": "any", "timeout_s": 5, "channel_id": "link_a"}',
        ),
        capabilities=layer(),
    )

    answer = answer_to_call(messages=messages)
    assert answer.outcome == "success"
    assert answer.content == "any 5.0"


async def test_the_history_keeps_the_call_as_the_model_sent_it() -> None:
    """The stored history holds the arguments as sent.

    ``ToolCallInvoked`` is logged from the same tool-call part, so the event log matches.
    """
    sent = '{"wait_for": "any"}'
    messages = await run_agent(
        model=calling_once(tool_name="list_channels", args=sent),
        capabilities=layer(),
    )

    calls = [
        part
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    assert [call.args for call in calls] == [sent]


async def test_each_drop_is_logged_with_the_call_id(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        await run_agent(
            model=calling_once(tool_name="list_channels", args='{"wait_for": "any"}'),
            capabilities=layer(),
        )

    assert "viewer_a_4 called list_channels (call call-1)" in caplog.text
    assert "dropped: wait_for" in caplog.text


async def test_arguments_that_are_not_json_are_left_for_validation_to_report() -> None:
    messages = await run_agent(
        model=calling_once(tool_name="read_notifications", args='{"wait_for": "any"'),
        capabilities=layer(),
    )

    assert "json_invalid" in refusal(answer=answer_to_call(messages=messages))


def test_a_tool_that_accepts_extra_arguments_keeps_them() -> None:
    tool_def = ToolDefinition(
        name="free_form", parameters_json_schema={"type": "object", "properties": {}}
    )

    assert undeclared_arguments(arguments={"anything": 1}, tool_def=tool_def) == []


@pytest.mark.parametrize("provider", [Provider.SELF_HOSTED, Provider.OLLAMA, Provider.GROQ])
def test_an_agent_on_an_open_weight_provider_gets_the_layer(provider: Provider) -> None:
    capabilities = open_model_capabilities(provider=provider, agent_id="viewer_a_1")

    assert capabilities == [OpenModelAntiCorruptionLayer(agent_id="viewer_a_1")]


@pytest.mark.parametrize("provider", [Provider.ANTHROPIC, Provider.OPENAI, Provider.OPENROUTER])
def test_an_agent_on_a_closed_or_unclassified_provider_does_not(provider: Provider) -> None:
    """Anthropic and OpenAI serve closed weights; ``openrouter`` serves both, so it has no class."""
    assert open_model_capabilities(provider=provider, agent_id="viewer_a_1") == []
