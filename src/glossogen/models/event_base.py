"""Foundation types shared by every event subclass.

``EventBase`` is the Pydantic base every concrete event subclasses. It
intentionally does NOT declare ``event_type`` — every concrete subclass
declares its own ``event_type: Literal[...]`` so the discriminated-union
JSONL parser dispatches correctly. Declaring it on the base would force
every override to fight pyright's invariant-override check.
"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Token counts returned by the LLM for a single request/response cycle."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class EventBase(BaseModel):
    """Base model for all simulation events, providing a unique ID, UTC timestamp, and round.

    ``round_number`` is the round in which the event occurred. Lifecycle
    events that fire before round 1 (``SimulationStarted``,
    ``AgentRegistered``) carry ``round_number=0`` as a sentinel; every
    other event carries the round it was emitted in.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    round_number: int
