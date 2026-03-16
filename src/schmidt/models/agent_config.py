"""Pydantic model defining the configuration schema for a single agent in a simulation."""

from pydantic import BaseModel


class AgentConfig(BaseModel):
    """Configuration for one agent participating in a scenario.

    Specifies the agent's identity, system prompt, which communication
    channels it can access, and which tools it is allowed to invoke.
    """

    agent_id: str
    role_name: str
    system_prompt: str
    channel_ids: list[str]
    tool_names: list[str]
