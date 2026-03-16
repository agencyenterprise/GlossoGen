"""Channel model used to represent a communication channel between agents."""

from pydantic import BaseModel


class Channel(BaseModel):
    """A communication channel that groups a set of agents by their IDs."""

    channel_id: str
    name: str
    member_agent_ids: list[str]
