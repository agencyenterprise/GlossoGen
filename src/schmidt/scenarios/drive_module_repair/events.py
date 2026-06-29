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

    ``judge_expected_action`` is the canonical rendered description (naming the
    module) the LLM judge compares the technician's free-text action against.
    """

    step_index: int
    module_label: str
    component: str
    symptom: str
    tool: str
    torque_nm: int
    calibration: str
    access_depth: int
    judge_expected_action: str


class DriveModuleModulePanel(BaseModel):
    """The symptoms observed on one module's diagnostic panel this round."""

    module_label: str
    symptoms: list[str]


class DriveModuleCaseStarted(EventBase):
    """Emitted once at round start with the full ground-truth case.

    ``module_panels`` is what the field technician observes per module (private
    to A). ``fault_tree`` is the per-round symptom -> component mapping (private
    to the diagnostics engineer); ``spec_table`` is the per-round component ->
    tool/torque/calibration mapping (private to the spec engineer); both are
    shared across modules. ``stages`` is the derived ordered ground truth:
    modules in canonical order, components within each in access-depth order.
    """

    event_type: Literal["drive_module_case_started"] = "drive_module_case_started"
    case_number: int
    module_count: int
    replacement_count: int
    module_panels: list[DriveModuleModulePanel]
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
