"""How the runner drives a ``workspace_action`` agent's cycle.

A suspension call (``wait_for_message`` or ``finish``) is intercepted before any
tool runs, a tool-delivered ``done`` stops the cycle, and a failed request is
retried from the request that failed rather than from the cycle's first prompt.
"""

from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel
from pydantic_ai.usage import RunUsage

from glossogen.runners.pydantic_ai_runner import (
    _run_agent_call,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.runners.pydantic_ai_runner import (
    _RunCheckpoint,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.runners.pydantic_ai_runner import (
    _StreamingState,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.runners.wait_suspension import parse_wait_arguments


async def ungated(response: ModelResponse) -> None:
    """Run the response's tools at once, as a run without a virtual clock does."""
    _ = response


async def drain(ctx: RunContext[None], events: AsyncIterable[AgentStreamEvent]) -> None:
    """Consume a node's event stream without reacting to it."""
    _ = ctx
    async for _event in events:
        pass


def scripted(responses: list[ModelResponse]) -> FunctionModel:
    """A model answering request N with ``responses[N]``, streamed or not."""
    sent: list[int] = []

    def respond() -> ModelResponse:
        sent.append(1)
        return responses[len(sent) - 1]

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = messages, info
        return respond()

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        _ = messages, info
        response = respond()
        calls: DeltaToolCalls = {}
        for index, part in enumerate(response.parts):
            if isinstance(part, ToolCallPart):
                calls[index] = DeltaToolCall(
                    name=part.tool_name,
                    json_args=part.args_as_json_str(),
                    tool_call_id=part.tool_call_id,
                )
            elif isinstance(part, TextPart):
                yield part.content
        if calls:
            yield calls

    return FunctionModel(model, stream_function=stream)


async def run_cycle(
    agent: Agent[None, str], streaming: bool, intercept_wait: bool, state: _StreamingState
) -> Any:
    return await _run_agent_call(
        agent=agent,
        checkpoint=_RunCheckpoint(messages=None, prompt="start"),
        event_stream_handler=drain,
        max_tokens=100,
        record_usage=lambda _usage: None,
        non_streaming_model_requests=not streaming,
        state=state,
        flush_inter_call_response=lambda: None,
        stop_on_done=True,
        intercept_wait=intercept_wait,
        on_model_response=lambda _response: None,
        before_model_request=lambda: None,
        gate_model_response=ungated,
    )


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("tool_name", ["wait_for_message", "finish"])
async def test_a_lone_suspension_call_ends_the_cycle_before_any_tool_runs(
    streaming: bool, tool_name: str
) -> None:
    executed: list[str] = []
    agent = Agent(
        scripted(responses=[ModelResponse(parts=[ToolCallPart(tool_name, {}, "s1")])]),
        output_type=str,
    )

    @agent.tool_plain(name=tool_name)
    def suspend() -> str:  # pyright: ignore[reportUnusedFunction]
        executed.append(tool_name)
        return "never"

    outcome = await run_cycle(
        agent=agent, streaming=streaming, intercept_wait=True, state=_StreamingState()
    )
    assert outcome.kind == "suspended"
    assert executed == []
    assert [call.tool_call_id for call in outcome.tool_calls] == ["s1"]
    assert isinstance(outcome.history[-1], ModelResponse)


@pytest.mark.parametrize("streaming", [False, True])
async def test_a_suspension_call_beside_another_call_rejects_the_whole_response(
    streaming: bool,
) -> None:
    executed: list[str] = []
    agent = Agent(
        scripted(
            responses=[
                ModelResponse(
                    parts=[
                        ToolCallPart("act", {"command": "craft"}, "a1"),
                        ToolCallPart("wait_for_message", {}, "w1"),
                    ]
                )
            ]
        ),
        output_type=str,
    )

    @agent.tool_plain
    def act(command: str) -> str:  # pyright: ignore[reportUnusedFunction]
        executed.append(command)
        return "crafted"

    @agent.tool_plain
    def wait_for_message() -> str:  # pyright: ignore[reportUnusedFunction]
        executed.append("wait_for_message")
        return "never"

    outcome = await run_cycle(
        agent=agent, streaming=streaming, intercept_wait=True, state=_StreamingState()
    )
    assert outcome.kind == "rejected"
    assert executed == []
    assert [call.tool_name for call in outcome.tool_calls] == ["act", "wait_for_message"]


@pytest.mark.parametrize("done", [False, True])
async def test_a_tool_delivered_done_stops_the_cycle_without_another_request(done: bool) -> None:
    requests: list[int] = []
    responses = [
        ModelResponse(parts=[ToolCallPart("read_notifications", {}, "r1")]),
        ModelResponse(parts=[TextPart("finished")]),
    ]

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = messages, info
        requests.append(1)
        return responses[len(requests) - 1]

    agent = Agent(FunctionModel(model), output_type=str)

    @agent.tool_plain
    def read_notifications() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        if done:
            return {"type": "done"}
        return {"type": "new_info"}

    state = _StreamingState()

    async def handle(ctx: RunContext[None], events: AsyncIterable[AgentStreamEvent]) -> None:
        _ = ctx
        async for event in events:
            if isinstance(event, FunctionToolResultEvent):
                content: Any = event.part.content
                state.got_done = content["type"] == "done"

    usage: list[RunUsage] = []
    outcome = await _run_agent_call(
        agent=agent,
        checkpoint=_RunCheckpoint(messages=None, prompt="start"),
        event_stream_handler=handle,
        max_tokens=100,
        record_usage=usage.append,
        non_streaming_model_requests=True,
        state=state,
        flush_inter_call_response=lambda: None,
        stop_on_done=True,
        intercept_wait=True,
        on_model_response=lambda _response: None,
        before_model_request=lambda: None,
        gate_model_response=ungated,
    )
    assert len(requests) == 1 + (not done)
    assert (outcome.kind == "done") == done
    assert len(usage) == 1


async def test_a_retry_resumes_at_the_failed_request_with_the_prior_steps() -> None:
    """A model error mid-cycle must not replay the cycle from its first prompt.

    Otherwise an agent that had already read its one-shot task card comes back
    with no card and no memory of the crafts it made.
    """
    requests: list[list[ModelMessage]] = []
    tool_runs: list[str] = []
    failed: list[bool] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = info
        requests.append(messages)
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step == 0:
            return ModelResponse(parts=[ToolCallPart("read_notifications", {}, "call1")])
        if step == 1:
            return ModelResponse(parts=[ToolCallPart("act", {"command": "craft"}, "call2")])
        if not failed:
            failed.append(True)
            raise ModelHTTPError(status_code=400, model_name="test", body="context length")
        return ModelResponse(parts=[TextPart("finished")])

    agent = Agent(FunctionModel(model), output_type=str)

    @agent.tool_plain
    def read_notifications() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        tool_runs.append("read_notifications")
        return {"type": "new_info", "text": "TASK: r956917"}

    @agent.tool_plain
    def act(command: str) -> str:  # pyright: ignore[reportUnusedFunction]
        tool_runs.append(command)
        return "crafted"

    outcome = await run_cycle(
        agent=agent, streaming=False, intercept_wait=False, state=_StreamingState()
    )
    assert outcome.result.output == "finished"
    assert tool_runs == ["read_notifications", "craft"]
    retried = ModelMessagesTypeAdapter.dump_json(requests[-1]).decode()
    assert "TASK: r956917" in retried
    assert "crafted" in retried
    assert retried.count('"start"') == 1


def test_suspension_arguments_parse_into_their_kind_and_deadline() -> None:
    assert parse_wait_arguments(part=ToolCallPart("finish", {"note": "done"}, "f1")) == (
        "finish",
        None,
    )
    assert parse_wait_arguments(part=ToolCallPart("wait_for_message", {"timeout_s": 5}, "w1")) == (
        "message",
        5.0,
    )
    with pytest.raises(ValueError, match="wait_for_message arguments are invalid"):
        parse_wait_arguments(part=ToolCallPart("wait_for_message", {"until": {}}, "w2"))
