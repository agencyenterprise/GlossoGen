"""Transient event types for real-time SSE streaming.

These events are pushed via the EventBus and SSE but are NOT persisted
to the simulation JSONL event log.
"""

from typing import Literal

from pydantic import BaseModel


class AgentCostUpdated(BaseModel):
    """Cumulative cost snapshot for a single agent after a run cycle.

    Published after each ``agent.run()`` cycle completes and token usage
    is tallied. The frontend accumulates per-agent costs and sums them
    for the displayed total. Not persisted — the final total arrives in
    ``SimulationEnded``.
    """

    event_type: Literal["agent_cost_updated"] = "agent_cost_updated"
    agent_id: str
    cumulative_cost_usd: float


class DebugLogEmitted(BaseModel):
    """A debug log record from the simulation process.

    Published to the EventBus by a custom logging handler so the frontend
    can display logs in real time. The same data is also written to the
    debug JSONL file for completed-run access via REST.
    """

    event_type: Literal["debug_log"] = "debug_log"
    timestamp: str
    logger_name: str
    level: str
    message: str
