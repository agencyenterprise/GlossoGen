"""Pydantic models representing messages exchanged between agents during a simulation."""

from datetime import datetime

from pydantic import BaseModel


class SimulationMessage(BaseModel):
    """A single message sent by an agent on a channel during a simulation run."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
