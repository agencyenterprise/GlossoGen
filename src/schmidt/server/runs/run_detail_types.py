"""Leaf DTOs shared by run-detail consumers and scenario extensions.

Lives outside :mod:`schmidt.server.runs.models` so that
:mod:`schmidt.server.runs.scenario_extension` (and scenario-side
``run_detail_extension`` modules it auto-discovers) can import these types
without triggering the import cycle that would otherwise form against
:data:`schmidt.server.runs.models.RunDetailResponse`.
"""

from datetime import datetime

from pydantic import BaseModel


class AgentDetail(BaseModel):
    """Full agent information for the run detail endpoint."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    model: str
    provider: str
    system_prompt: str


class ChannelMessage(BaseModel):
    """A message sent by an agent to a channel."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    round_number: int
    token_count: int
