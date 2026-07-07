"""Leaf DTOs shared by run-detail consumers and scenario extensions.

Lives outside :mod:`glossogen.server.runs.models` so that
:mod:`glossogen.server.runs.scenario_extension` (and scenario-side
``run_detail_extension`` modules it auto-discovers) can import these types
without triggering the import cycle that would otherwise form against
:data:`glossogen.server.runs.models.RunDetailResponse`.
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
    sender_display_name: str
    text: str
    timestamp: datetime
    round_number: int
    token_count: int


class JudgeGroundTruthMetadata(BaseModel):
    """LLM-judge ground truth for a single judged action tool call.

    Scenarios whose executor submits a free-text action scored by an LLM
    judge surface the same three facts per call, attached by tool ``call_id``.
    """

    expected_actions: str
    judge_match: bool
    judge_explanation: str
