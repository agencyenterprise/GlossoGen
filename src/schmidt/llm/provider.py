"""Abstract base types for LLM integration.

Defines the message, response, and provider interfaces that concrete LLM
implementations must conform to.
"""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

from schmidt.models.event import TokenUsage
from schmidt.models.tool_definition import ToolCallRequest, ToolSpec

T = TypeVar("T", bound=BaseModel)


class LLMMessage(BaseModel):
    """A single message in a conversation, with a role and content payload."""

    role: str
    content: str | list[dict[str, Any]]


class LLMResponse(BaseModel):
    """The result returned by an LLM provider after generating a completion.

    Captures the generated text, any tool call requests, the reason generation
    stopped, token usage counts, and the raw provider-specific content blocks.
    """

    text: str | None
    tool_calls: list[ToolCallRequest]
    stop_reason: str
    usage: TokenUsage
    raw_content: list[dict[str, Any]]


class LLMProvider(ABC):
    """Abstract interface for LLM providers.

    Concrete subclasses implement ``generate`` for free-form LLM calls and
    ``generate_structured`` for calls that must return a validated Pydantic model.
    """

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        tools: list[ToolSpec],
    ) -> LLMResponse:
        """Send a conversation to the LLM and return its response.

        Args:
            system_prompt: The system-level instruction for the model.
            messages: The conversation history as a list of messages.
            tools: Tool specifications the model may invoke.

        Returns:
            The model's response including text, tool calls, and usage data.
        """
        ...

    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[T],
    ) -> T:
        """Send a conversation to the LLM and return a validated Pydantic model.

        The provider converts the output_schema into a tool definition,
        forces the model to call it, and validates the response against
        the schema.

        Args:
            system_prompt: The system-level instruction for the model.
            messages: The conversation history as a list of messages.
            output_schema: The Pydantic model class defining the output shape.

        Returns:
            A validated instance of the output_schema.
        """
        ...
