"""Pydantic models representing messages exchanged between agents during a simulation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, model_validator


class SimulationMessage(BaseModel):
    """A single message sent by an agent on a channel during a simulation run.

    ``sender_display_name`` is captured at send time using the scenario's
    ``get_agent_display_name_at_round`` so historical messages render under
    the display name the slot held when they were sent (relevant for
    scenarios that rotate identity behind a single ``agent_id``, e.g.
    surprise_party's friend slot).
    """

    message_id: str
    channel_id: str
    sender_agent_id: str
    sender_display_name: str
    text: str
    timestamp: datetime
    round_number: int

    @model_validator(mode="before")
    @classmethod
    def _backfill_sender_display_name(cls, data: Any) -> Any:
        if (
            isinstance(data, dict)
            and "sender_display_name" not in data
            and "sender_agent_id" in data
        ):
            data = {**data, "sender_display_name": data["sender_agent_id"]}
        return data
