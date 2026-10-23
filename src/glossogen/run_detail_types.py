"""Leaf DTOs shared by run-detail consumers and scenario extensions.

Lives outside :mod:`glossogen.server` so that the scenario contract, through
:mod:`glossogen.scenario_run_detail_extension`, can name these types without
depending on the server package, and outside :mod:`glossogen.server.runs.models`
so that importing them does not build :data:`RunDetailResponse`.
"""

from datetime import datetime

from pydantic import BaseModel
from pydantic_ai.settings import ThinkingLevel


class AgentDetail(BaseModel):
    """Full agent information for the run detail endpoint.

    ``thinking`` is the level the agent was sent, ``None`` for the model's default.
    """

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    model: str
    provider: str
    thinking: ThinkingLevel | None
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
