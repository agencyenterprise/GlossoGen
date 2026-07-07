"""Pydantic event types specific to the spillway_release scenario.

Imports only from :mod:`glossogen.models.event_base` so the discovered-union
JSONL parser can load this module without triggering the event-discovery
import cycle.
"""

from typing import Literal

from glossogen.models.event_base import EventBase


class SpillwayCaseStarted(EventBase):
    """Emitted once at round start with the full ground-truth case.

    ``current_time_hours`` and ``day_end_hours`` are shared with all three
    agents. ``start_level`` is private to the dam operator, ``inflow`` and
    ``forecast_conditions`` private to civil defense, and
    ``park_opens_at_hours`` / ``park_lockable`` / ``visitors`` private to the
    park ranger. ``park_opens_at_hours`` is ``None`` when the park is closed
    all day. The dam physics constants are echoed for downstream tooling.
    """

    event_type: Literal["spillway_case_started"] = "spillway_case_started"
    case_number: int
    current_time_hours: float
    start_level: int
    inflow: int
    forecast_conditions: str
    park_opens_at_hours: float | None
    park_lockable: bool
    visitors: int
    day_end_hours: float
    gate_count: int
    release_per_gate_per_hour: int
    max_level: int
    min_level: int
    round_time_budget_seconds: int


class SpillwayGatesOpened(EventBase):
    """Emitted when the dam operator commits a gate setting via ``open_gates``.

    A round can carry several of these (the operator may revise the plan);
    the last one before round end is the binding decision.
    """

    event_type: Literal["spillway_gates_opened"] = "spillway_gates_opened"
    agent_id: str
    gate_count_opened: int
    duration_hours: float
    release_total: float
    window_start_hours: float
    window_end_hours: float


class SpillwayParkNotified(EventBase):
    """Emitted when the park ranger calls ``notify_park``.

    ``accepted`` is false when the park is committed-open (not lockable) and
    the securing request was rejected.
    """

    event_type: Literal["spillway_park_notified"] = "spillway_park_notified"
    agent_id: str
    action: Literal["close", "keep_closed"]
    accepted: bool


class SpillwayEvacuated(EventBase):
    """Emitted when civil defense calls ``evacuate`` to clear the downstream area."""

    event_type: Literal["spillway_evacuated"] = "spillway_evacuated"
    agent_id: str


class SpillwayRoundResolved(EventBase):
    """Emitted at round end with the deterministic per-clause verdict.

    Carries the resolved end level and every success clause so the FE and
    downstream tooling can read the full ground truth without recomputing it.
    """

    event_type: Literal["spillway_round_resolved"] = "spillway_round_resolved"
    case_number: int
    end_level: float
    release_total: float
    would_overlap: bool
    clearing_was_needed: bool
    park_secured: bool
    evacuated: bool
    budget_exceeded: bool
    dam_ok: bool
    casualties: bool
    needless_closure: bool
    false_alarm: bool
    round_succeeded: bool
    failure_reason: str
