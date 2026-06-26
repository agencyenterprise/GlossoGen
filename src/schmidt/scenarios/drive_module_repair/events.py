"""Pydantic event types specific to the drive_module_repair scenario.

Imports only from :mod:`schmidt.models.event_base` so the discovered-union
JSONL parser can load this module without triggering the event-discovery
import cycle.
"""

from typing import Literal

from pydantic import BaseModel

from schmidt.models.event_base import EventBase


class DriveModuleFaultEntry(BaseModel):
    """One row of the per-round fault-tree: a symptom and the component it indicates."""

    symptom: str
    component: str


class DriveModuleSpecEntry(BaseModel):
    """One row of the per-round service-spec table for a component."""

    component: str
    tool: str
    torque_nm: int
    calibration: str


class DriveModuleStage(BaseModel):
    """One ordered replacement the technician must perform, with its ground truth.

    ``judge_expected_action`` is the canonical rendered description the LLM
    judge compares the technician's free-text action against.
    """

    step_index: int
    component: str
    symptom: str
    tool: str
    torque_nm: int
    calibration: str
    access_depth: int
    judge_expected_action: str


class DriveModuleCaseStarted(EventBase):
    """Emitted once at round start with the full ground-truth case.

    ``panel_symptoms`` is what the field technician observes (private to A).
    ``fault_tree`` is the per-round symptom -> component mapping (private to
    the diagnostics engineer). ``spec_table`` is the per-round component ->
    tool/torque/calibration mapping (private to the spec engineer).
    ``stages`` is the derived ordered ground truth (faulty components in
    access-depth order, each fully specified).
    """

    event_type: Literal["drive_module_case_started"] = "drive_module_case_started"
    case_number: int
    replacement_count: int
    panel_symptoms: list[str]
    fault_tree: list[DriveModuleFaultEntry]
    spec_table: list[DriveModuleSpecEntry]
    stages: list[DriveModuleStage]
    round_time_budget_seconds: int


class DriveModuleReplacementJudged(EventBase):
    """Emitted after the LLM judge rules on a ``replace_component`` call."""

    event_type: Literal["drive_module_replacement_judged"] = "drive_module_replacement_judged"
    agent_id: str
    step_index: int
    expected_action: str
    technician_action: str
    judge_match: bool
    judge_explanation: str
