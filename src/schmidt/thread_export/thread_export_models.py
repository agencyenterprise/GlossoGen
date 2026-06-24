"""Typed envelope for an exported agent thread plus the provider-native request bodies.

``ThreadExport`` wraps provenance (``meta``) around a ``request`` that is a
ready-to-POST body for the provider the agent ran under. The consumer appends
their own trailing user message (and ``max_tokens`` for Anthropic) and sends it
unchanged; the request models therefore carry only keys the provider accepts.

The Anthropic and OpenAI message shapes are modeled as discriminated unions so
the serialized JSON matches each provider's wire format exactly. ``input`` on a
tool-use block and ``arguments`` on an OpenAI tool call carry arbitrary
tool-defined JSON, so they are typed as ``dict[str, Any]`` / ``str``
respectively.
"""

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Discriminator, model_serializer


class AnthropicTextBlock(BaseModel):
    """Anthropic ``text`` content block."""

    type: Literal["text"] = "text"
    text: str


class AnthropicToolUseBlock(BaseModel):
    """Anthropic ``tool_use`` content block carrying the call's arguments object."""

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class AnthropicToolResultBlock(BaseModel):
    """Anthropic ``tool_result`` content block referencing the originating call."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str


AnthropicBlock = Annotated[
    Union[AnthropicTextBlock, AnthropicToolUseBlock, AnthropicToolResultBlock],
    Discriminator("type"),
]


class AnthropicMessage(BaseModel):
    """One Anthropic message turn with role-tagged content blocks."""

    role: Literal["user", "assistant"]
    content: list[AnthropicBlock]


class AnthropicRequest(BaseModel):
    """Drop-in Anthropic Messages API body (minus ``max_tokens`` and the trailing question)."""

    model: str
    system: str
    messages: list[AnthropicMessage]


class OpenAIFunctionCall(BaseModel):
    """The ``function`` payload of an OpenAI tool call (arguments as a JSON string)."""

    name: str
    arguments: str


class OpenAIToolCall(BaseModel):
    """One OpenAI assistant tool call."""

    id: str
    type: Literal["function"] = "function"
    function: OpenAIFunctionCall


class OpenAISystemMessage(BaseModel):
    """OpenAI ``system`` message."""

    role: Literal["system"] = "system"
    content: str


class OpenAIUserMessage(BaseModel):
    """OpenAI ``user`` message."""

    role: Literal["user"] = "user"
    content: str


class OpenAIAssistantMessage(BaseModel):
    """OpenAI ``assistant`` message.

    Carries text ``content`` and/or ``tool_calls``; the unused field is dropped
    on serialization (``model_dump(exclude_none=True)``) so the body matches the
    provider's accepted shape for each turn.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: list[OpenAIToolCall] | None = None

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        """Emit only the fields set for this turn so the body matches OpenAI's shape.

        A text-only turn drops ``tool_calls``; a tool-call-only turn drops
        ``content``. Both are kept when the assistant turn carried text and
        tool calls together.
        """
        payload: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            payload["content"] = self.content
        if self.tool_calls is not None:
            payload["tool_calls"] = [tool_call.model_dump() for tool_call in self.tool_calls]
        return payload


class OpenAIToolMessage(BaseModel):
    """OpenAI ``tool`` message returning one tool call's result."""

    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: str


OpenAIMessage = Annotated[
    Union[
        OpenAISystemMessage,
        OpenAIUserMessage,
        OpenAIAssistantMessage,
        OpenAIToolMessage,
    ],
    Discriminator("role"),
]


class OpenAIRequest(BaseModel):
    """Drop-in OpenAI Chat Completions body (minus the trailing question)."""

    model: str
    messages: list[OpenAIMessage]


class ThreadExportMeta(BaseModel):
    """Provenance describing which agent/run/round the exported thread came from."""

    run_id: str
    agent_id: str
    role_name: str
    model: str
    provider: str
    cutoff_round: int | None
    rounds_covered: str
    num_messages: int
    format: Literal["anthropic_messages", "openai_chat"]
    thinking_included: bool
    tools_flattened: bool
    exported_at: datetime


class ThreadExport(BaseModel):
    """Full export: provenance ``meta`` plus a drop-in provider ``request`` body."""

    meta: ThreadExportMeta
    request: AnthropicRequest | OpenAIRequest
