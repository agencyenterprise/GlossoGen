"""Result model returned by agent runners after completion."""

from pydantic import BaseModel


class AgentRunResult(BaseModel):
    """Captures the outcome of a single agent's run."""

    agent_id: str
    total_cost_usd: float
    total_turns: int
