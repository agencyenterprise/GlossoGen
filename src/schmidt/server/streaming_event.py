"""Transient event types for real-time SSE streaming.

These events are pushed via the EventBus and SSE but are NOT persisted
to the simulation JSONL event log.
"""

from typing import Literal

from pydantic import BaseModel


class TokenDelta(BaseModel):
    """A partial text chunk from an in-progress LLM response.

    Emitted token-by-token as the Claude streaming API produces output. The
    ``is_final`` flag signals that the LLM response is complete and the partial
    text accumulator should be cleared.
    """

    event_type: Literal["token_delta"] = "token_delta"
    agent_id: str
    text: str
    is_final: bool
    round_number: int


class MessagePreview(BaseModel):
    """A partial text preview of an in-progress send_message tool call.

    Emitted as the LLM streams the text argument of send_message. The
    ``channel_id`` identifies where the message will be posted. Replaced
    by the final MessageSent event when the tool call completes.
    """

    event_type: Literal["message_preview"] = "message_preview"
    agent_id: str
    channel_id: str
    text: str
    is_final: bool
    round_number: int


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
