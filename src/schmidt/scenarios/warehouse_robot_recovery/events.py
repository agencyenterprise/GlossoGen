"""Pydantic event types specific to the warehouse_robot_recovery scenario."""

from typing import Literal

from pydantic import BaseModel

from schmidt.models.event_base import EventBase


class WarehouseFaultRecovery(BaseModel):
    """One fault present on the round's robot, plus its recovery procedure."""

    fault_name: str
    observable_symptoms: list[str]
    recovery_procedure: str
    wait_seconds: int


class WarehouseCaseStarted(EventBase):
    """Emitted once at round start with full ground-truth case data.

    Evaluators read robot identity, fault list, recovery procedures, and
    safety state directly from this event so they do not have to reparse
    free-form injection text.
    """

    event_type: Literal["warehouse_case_started"] = "warehouse_case_started"
    case_number: int
    robot_id: str
    aisle: str
    bay: str
    robot_model: str
    firmware_state: str
    fleet_mode: str
    faults: list[WarehouseFaultRecovery]
    required_step_order: list[str]
    forbidden_actions: list[str]
    aisle_locked: bool
    safety_notes: list[str]
    time_budget_seconds: int


class WarehouseRecoveryJudgment(BaseModel):
    """Structured per-criterion verdict from the recovery judge."""

    targets_correct_robot: bool
    addresses_all_faults: bool
    correct_order: bool
    correct_wait_times: bool
    respects_safety_constraints: bool
    no_forbidden_actions: bool
    final_state_safe: bool


class WarehouseRecoveryJudged(EventBase):
    """Emitted after the recovery judge rules on a ``perform_recovery`` call.

    Captures the ground-truth expected procedure, the safety constraints,
    the per-criterion judge verdict, and the judge's free-form explanation
    so the frontend can show full context alongside the ``ToolResultReceived``.
    """

    event_type: Literal["warehouse_recovery_judged"] = "warehouse_recovery_judged"
    agent_id: str
    robot_id: str
    expected_procedure: str
    safety_constraints: str
    judgment: WarehouseRecoveryJudgment
    overall_success: bool
    budget_exceeded: bool
    judge_explanation: str
