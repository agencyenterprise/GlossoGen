"""Abstract base types for LLM integration.

Defines the message and provider interfaces that concrete LLM
implementations must conform to. Used by evaluation for LLM-as-judge.
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from schmidt.evaluation.reports.evaluation_cost import EvaluationTokenUsage

T = TypeVar("T", bound=BaseModel)


class LLMMessage(BaseModel):
    """A single message in a conversation, with a role and content payload."""

    role: str
    content: str


class LLMProvider(ABC):
    """Abstract interface for LLM providers.

    Concrete subclasses implement ``generate_structured`` for calls that
    must return a validated Pydantic model. Used by evaluation for
    LLM-as-judge scoring. Token usage is accumulated across calls and
    can be read via ``get_accumulated_usage()``.
    """

    def __init__(self) -> None:
        """Initialize the token usage accumulators to zero."""
        self._input_tokens = 0
        self._output_tokens = 0
        self._cache_read_input_tokens = 0
        self._cache_creation_input_tokens = 0

    def _record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int,
        cache_creation_input_tokens: int,
    ) -> None:
        """Add token counts from a single API call to the running totals."""
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        self._cache_read_input_tokens += cache_read_input_tokens
        self._cache_creation_input_tokens += cache_creation_input_tokens

    def get_accumulated_usage(self) -> EvaluationTokenUsage:
        """Return the accumulated token usage across all calls made by this provider."""
        return EvaluationTokenUsage(
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            cache_read_input_tokens=self._cache_read_input_tokens,
            cache_creation_input_tokens=self._cache_creation_input_tokens,
        )

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
