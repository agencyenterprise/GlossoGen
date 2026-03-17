"""Channel model used to represent a communication channel between agents."""

from typing import NamedTuple

from pydantic import BaseModel


class Channel(BaseModel):
    """A communication channel that groups a set of agents by their IDs."""

    channel_id: str
    name: str
    member_agent_ids: list[str]


class ChannelTemplateEntry(NamedTuple):
    """A channel's display name and ID, passed to Jinja2 system prompt templates."""

    display_name: str
    channel_id: str
