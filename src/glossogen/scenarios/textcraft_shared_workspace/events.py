"""Evaluator-only ground truth, isolated from runtime imports for event discovery."""

from typing import Any, Literal

from glossogen.models.event_base import EventBase


class WorkspaceTaskStarted(EventBase):
    """The full task manifest, never a broadcast to agents."""

    event_type: Literal["workspace_task_started"] = "workspace_task_started"
    round_number: int
    task_id: str
    manifest: dict[str, Any]
    comms_enabled: bool


class WorkspaceRecipesDealt(EventBase):
    """Which recipes each agent was dealt, when a pool agent holds only some of them."""

    event_type: Literal["workspace_recipes_dealt"] = "workspace_recipes_dealt"
    round_number: int
    task_id: str
    holders: int
    hands: dict[str, list[str]]


class WorkspaceActionExecuted(EventBase):
    """An ordered action and its true resource provenance."""

    event_type: Literal["workspace_action_executed"] = "workspace_action_executed"
    round_number: int
    agent_id: str
    command: str
    accepted: bool
    version: int
    delta: dict[str, int]
    depot: dict[str, int]
    consumed_from: list[tuple[str, str, int]]
    observation: str
    virtual_time_s: float | None = None
    """Virtual seconds since the round started, when the run simulates API latency."""


class WorkspaceCraftCompleted(EventBase):
    """A timed craft's output landing, after its ``WorkspaceActionExecuted`` start.

    Logged only when ``craft_duration_s`` is set; the start event's delta then
    holds the consumed inputs and this one's delta the output.
    """

    event_type: Literal["workspace_craft_completed"] = "workspace_craft_completed"
    round_number: int
    agent_id: str
    command: str
    version: int
    delta: dict[str, int]
    depot: dict[str, int]
    started_at_s: float
    virtual_time_s: float


class WorkspaceMessageContextDelivered(EventBase):
    """Public message bodies included in one agent-facing tool result."""

    event_type: Literal["workspace_message_context_delivered"] = (
        "workspace_message_context_delivered"
    )
    round_number: int
    agent_id: str
    channel_id: str
    delivery_carrier: Literal["act", "send", "observe", "wake"]
    message_ids: list[str]


class WorkspaceRoundResolved(EventBase):
    """Deterministic outcome and process counts, including failed rounds."""

    event_type: Literal["workspace_round_resolved"] = "workspace_round_resolved"
    round_number: int
    task_id: str
    success: bool
    trigger: str
    characters_used: int
    actions_used: dict[str, int]
    transitions: int
    failed_crafts: int
    targets_satisfied: int
    depot: dict[str, int]
    virtual_elapsed_seconds: float | None = None
    """Virtual seconds from round start to its terminal condition (the makespan on
    success), when the run simulates API latency."""
