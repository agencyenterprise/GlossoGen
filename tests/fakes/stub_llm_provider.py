"""An LLMProvider that returns answers the test chose in advance.

Scenarios that judge their own rounds build a provider when they are
constructed, and the judge metrics call one directly, so a test that never
touches the network still needs something shaped like a provider.

Answers come from a queue. Every call is recorded, which is usually the more
interesting assertion: not what the judge said, but what it was shown.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from glossogen.llm.provider import LLMMessage, LLMProvider, SamplingParams

T = TypeVar("T", bound=BaseModel)


@dataclass
class RecordedCall:
    """One ``generate_structured`` call, kept so tests can assert on the prompt."""

    system_prompt: str
    messages: list[LLMMessage]
    output_schema: type[BaseModel]


@dataclass
class StubLLMProvider(LLMProvider):
    """Return queued responses in order; record every call."""

    responses: deque[BaseModel] = field(default_factory=deque[BaseModel])
    calls: list[RecordedCall] = field(default_factory=list[RecordedCall])

    def __post_init__(self) -> None:
        """Initialise the token accumulators the base class owns."""
        super().__init__()

    def queue(self, *, response: BaseModel) -> None:
        """Add a response to be returned by the next call."""
        self.responses.append(response)

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[T],
        sampling: SamplingParams | None = None,
    ) -> T:
        """Return the next queued response, recording what was asked."""
        _ = sampling
        self.calls.append(
            RecordedCall(
                system_prompt=system_prompt,
                messages=list(messages),
                output_schema=output_schema,
            )
        )
        if not self.responses:
            raise AssertionError(
                f"judge called {len(self.calls)} time(s) but no response was queued for this one; "
                f"schema was {output_schema.__name__}"
            )
        response = self.responses.popleft()
        if not isinstance(response, output_schema):
            raise AssertionError(
                f"queued a {type(response).__name__} but the caller asked for "
                f"{output_schema.__name__}"
            )
        self._record_usage(
            input_tokens=0,
            output_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        return response
