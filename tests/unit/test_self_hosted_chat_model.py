"""A self-hosted model gets a system message only at the start of each request.

The servers behind the self-hosted provider render each request with the served model's chat
template, and Qwen3.8's template rejects a system message anywhere but first.
"""

import json
from functools import partial

import httpx2
import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.providers.openai import OpenAIProvider

from glossogen.llm import pydantic_ai_model_factory
from glossogen.llm.pydantic_ai_model_factory import build_pydantic_ai_model
from glossogen.model_catalog.provider_catalog import (
    SELF_HOSTED_API_KEY_VAR,
    SELF_HOSTED_BASE_URLS_VAR,
    Provider,
)

MODEL = "qwen-under-test"
SYSTEM_PROMPT = "You are player_b."


class SentMessage(BaseModel):
    """One chat message of a request that the server received."""

    role: str
    content: str | None


class SentRequest(BaseModel):
    """The messages of a chat completion request that the server received."""

    messages: list[SentMessage]


class ScriptedChatServer:
    """An OpenAI-compatible chat endpoint that answers each request with the next scripted text."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.requests: list[SentRequest] = []

    def respond(self, request: httpx2.Request) -> httpx2.Response:
        """Keep the request's messages and answer with the next reply, with no tool calls."""
        self.requests.append(SentRequest.model_validate_json(request.content))
        content = self.replies[len(self.requests) - 1]
        return httpx2.Response(
            status_code=200,
            json={
                "id": f"chatcmpl-{len(self.requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            },
        )


def serve_self_hosted_model(
    replies: list[str], monkeypatch: pytest.MonkeyPatch
) -> ScriptedChatServer:
    """Point the self-hosted provider's model at a scripted server that answers with ``replies``."""
    server = ScriptedChatServer(replies=replies)
    monkeypatch.setenv(SELF_HOSTED_BASE_URLS_VAR, json.dumps({MODEL: "http://vllm.test/v1"}))
    monkeypatch.setenv(SELF_HOSTED_API_KEY_VAR, "test-key")
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler=server.respond))
    monkeypatch.setattr(
        pydantic_ai_model_factory,
        "PydanticAIOpenAIProvider",
        partial(OpenAIProvider, http_client=client),
    )
    return server


def self_hosted_agent() -> Agent[None, str]:
    return Agent(
        model=build_pydantic_ai_model(model=MODEL, provider=Provider.SELF_HOSTED),
        system_prompt=SYSTEM_PROMPT,
    )


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


async def test_the_only_system_message_is_the_agents_prompt_as_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unless the model class turns it off, pydantic-ai sends a sentence about its ``<system>``
    tag as a second system message, which Qwen3.8's chat template also rejects."""
    server = serve_self_hosted_model(replies=["Done."], monkeypatch=monkeypatch)

    await self_hosted_agent().run(user_prompt="Your move.")

    sent = server.requests[0].messages
    system_messages = [message for message in sent if message.role == "system"]
    assert system_messages == [SentMessage(role="system", content=SYSTEM_PROMPT)]
