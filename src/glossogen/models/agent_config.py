"""Pydantic model defining the configuration schema for a single agent in a simulation."""

from typing import NamedTuple

from pydantic import BaseModel, ConfigDict
from pydantic_ai.messages import ModelMessage

from glossogen.models.compaction_config import CompactionConfig


class AgentRole(NamedTuple):
    """Lightweight agent identity returned by scenario discovery endpoints."""

    agent_id: str
    role_name: str


class AgentConfig(BaseModel):
    """Configuration for one agent participating in a scenario.

    Specifies the agent's identity, system prompt, which communication
    channels it can access, and which tools it is allowed to invoke.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_id: str
    role_name: str
    system_prompt: str
    channel_ids: list[str]
    tool_names: list[str]
    model: str
    provider: str
    max_tokens: int
    compaction: CompactionConfig
    initial_message_history: list[ModelMessage] | None = None
