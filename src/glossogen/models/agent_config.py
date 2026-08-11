"""The two views of an agent, before and after a scenario is built.

``AgentRole`` is just an id and a display name, available from the scenario class
without constructing it. The API uses it to show who will take part before a run
exists.

``AgentConfig`` is the full definition handed to a runner: the rendered system
prompt, which channels and tools the agent may touch, and which model answers for
it. Per-agent model overrides are already resolved by the time one is built.
"""

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
