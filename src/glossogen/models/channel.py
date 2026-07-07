"""Channel model used to represent a communication channel between agents."""

from typing import NamedTuple

from pydantic import BaseModel, Field


class Channel(BaseModel):
    """A communication channel that groups a set of agents by their IDs.

    ``member_join_index`` records, for members who joined after the channel
    was created, how many messages existed when they were added. Reads for
    that member return only messages from their join index onward. Members
    present at channel creation have no entry and see full history.
    """

    channel_id: str
    name: str
    member_agent_ids: list[str]
    member_join_index: dict[str, int] = Field(default_factory=dict)


class ChannelTemplateEntry(NamedTuple):
    """A channel's display name and ID, passed to Jinja2 system prompt templates."""

    display_name: str
    channel_id: str
