"""A self-hosted model gets a system message only at the start of each request.

The servers behind the self-hosted provider render each request with the served model's chat
template, and Qwen3.8's template rejects a system message anywhere but first.
"""

import json
from functools import partial
from typing import NamedTuple

import httpx2
import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from glossogen.llm import pydantic_ai_model_factory
from glossogen.llm.pydantic_ai_model_factory import (
    AGENT_ID_HEADER,
    RUN_ID_HEADER,
    agent_model_settings,
    build_pydantic_ai_model,
)
from glossogen.llm.self_hosted_chat_model import SelfHostedChatModel
from glossogen.model_catalog.provider_catalog import (
    SELF_HOSTED_API_KEY_VAR,
    SELF_HOSTED_BASE_URLS_VAR,
    Provider,
)
from glossogen.models.agent_model_settings import AgentModelSettings

MODEL = "qwen-under-test"
BASE_URL = "http://vllm.test/v1"
API_KEY = "test-key"
SYSTEM_PROMPT = "You are player_b."


class ToolCallReply(NamedTuple):
    """A scripted reply that calls one tool."""

    tool_name: str
    arguments: str


class SentMessage(BaseModel):
    """One chat message of a request that the server received."""

    role: str
    content: str | None


class SentRequest(BaseModel):
    """The messages of a chat completion request that the server received."""

    messages: list[SentMessage]


class ScriptedChatServer:
    """An OpenAI-compatible chat endpoint that answers each request with the next scripted reply.

    A ``str`` reply is the assistant's text, and ``""`` is an empty response.
    """

    def __init__(self, replies: list[str | ToolCallReply]) -> None:
        self.replies = replies
        self.requests: list[SentRequest] = []
        self.bodies: list[str] = []
        self.headers: list[httpx2.Headers] = []

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        """Keep the request and answer with the next reply."""
        self.headers.append(request.headers)
        self.bodies.append(request.content.decode())
        self.requests.append(SentRequest.model_validate_json(json_data=request.content))
        reply = self.replies[len(self.requests) - 1]
        message: dict[str, object] = {"role": "assistant", "content": reply}
        finish_reason = "stop"
        if isinstance(reply, ToolCallReply):
            call = {"name": reply.tool_name, "arguments": reply.arguments}
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": f"call-{len(self.requests)}", "type": "function", "function": call}
                ],
            }
            finish_reason = "tool_calls"
        return httpx2.Response(
            status_code=200,
            json={
                "id": f"chatcmpl-{len(self.requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": MODEL,
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            },
        )

    def client(self) -> httpx2.AsyncClient:
        """An HTTP client whose requests this server answers."""
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler=self.respond))


def serve_self_hosted_model(
    replies: list[str | ToolCallReply], monkeypatch: pytest.MonkeyPatch
) -> ScriptedChatServer:
    """Point the self-hosted provider's model at a scripted server that answers with ``replies``."""
    server = ScriptedChatServer(replies=replies)
    monkeypatch.setenv(name=SELF_HOSTED_BASE_URLS_VAR, value=json.dumps(obj={MODEL: BASE_URL}))
    monkeypatch.setenv(name=SELF_HOSTED_API_KEY_VAR, value=API_KEY)
    monkeypatch.setattr(
        target=pydantic_ai_model_factory,
        name="PydanticAIOpenAIProvider",
        value=partial(OpenAIProvider, http_client=server.client()),
    )
    return server


def move(direction: str) -> str:
    """Move the figure one square."""
    return f"You moved {direction}."


def agent_on(model: OpenAIChatModel | str) -> Agent[None, str]:
    """An agent with the ``move`` tool."""
    return Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[move])


def self_hosted_agent() -> Agent[None, str]:
    return agent_on(model=build_pydantic_ai_model(model=MODEL, provider=Provider.SELF_HOSTED))


async def test_feedback_after_an_empty_response_goes_out_as_a_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pydantic-ai answers an empty response with feedback that asks for output.

    Sent as a system message after the first, Qwen3.8's chat template refused it, and vLLM
    answered HTTP 400 to every retry of the request.
    """
    server = serve_self_hosted_model(replies=["", "Done."], monkeypatch=monkeypatch)

    await self_hosted_agent().run(user_prompt="Your move.")

    retry = server.requests[1]
    assert [message.role for message in retry.messages] == ["system", "user", "user"]


async def test_feedback_after_a_tool_result_is_not_a_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In the runs that failed, the empty response came right after a tool result."""
    replies: list[str | ToolCallReply] = [
        ToolCallReply(tool_name="move", arguments='{"direction": "down"}'),
        "",
        "Done.",
    ]
    server = serve_self_hosted_model(replies=replies, monkeypatch=monkeypatch)

    await self_hosted_agent().run(user_prompt="Your move.")

    retry = server.requests[2]
    assert retry.messages[-2].role == "tool"
    assert "system" not in [message.role for message in retry.messages[1:]]


async def test_the_only_system_message_is_the_agents_prompt_as_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unless the model class turns it off, pydantic-ai adds a sentence about its ``<system>``
    tag to the start of every request."""
    server = serve_self_hosted_model(replies=["Done."], monkeypatch=monkeypatch)

    await self_hosted_agent().run(user_prompt="Your move.")

    sent = server.requests[0].messages
    system_messages = [message for message in sent if message.role == "system"]
    assert system_messages == [SentMessage(role="system", content=SYSTEM_PROMPT)]


async def test_a_run_without_an_empty_response_sends_what_openai_chat_model_sends() -> None:
    """Both models get a tool call, then text, and send the same request bodies."""
    replies: list[str | ToolCallReply] = [
        ToolCallReply(tool_name="move", arguments='{"direction": "down"}'),
        "Done.",
    ]
    servers = [ScriptedChatServer(replies=replies), ScriptedChatServer(replies=replies)]
    plain = OpenAIChatModel(
        model_name=MODEL,
        provider=OpenAIProvider(
            base_url=BASE_URL, api_key=API_KEY, http_client=servers[0].client()
        ),
    )
    self_hosted = SelfHostedChatModel(
        model_name=MODEL,
        provider=OpenAIProvider(
            base_url=BASE_URL, api_key=API_KEY, http_client=servers[1].client()
        ),
    )

    await agent_on(model=plain).run(user_prompt="Your move.")
    await agent_on(model=self_hosted).run(user_prompt="Your move.")

    assert len(servers[1].bodies) == 2
    assert [json.loads(s=body) for body in servers[1].bodies] == [
        json.loads(s=body) for body in servers[0].bodies
    ]


async def test_each_request_of_a_self_hosted_agent_carries_the_run_and_agent_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The headers come from the agent's settings and reach the server on every request."""
    replies: list[str | ToolCallReply] = [
        ToolCallReply(tool_name="move", arguments='{"direction": "down"}'),
        "Done.",
    ]
    server = serve_self_hosted_model(replies=replies, monkeypatch=monkeypatch)
    agent = Agent(
        model=build_pydantic_ai_model(model=MODEL, provider=Provider.SELF_HOSTED),
        system_prompt=SYSTEM_PROMPT,
        tools=[move],
        model_settings=agent_model_settings(
            provider=Provider.SELF_HOSTED,
            model=MODEL,
            settings=AgentModelSettings(),
            run_id="signal_game/1795184024",
            agent_id="player_b",
        ),
    )

    await agent.run(user_prompt="Your move.")

    sent = [(each[RUN_ID_HEADER], each[AGENT_ID_HEADER]) for each in server.headers]
    assert sent == [("signal_game/1795184024", "player_b")] * 2
