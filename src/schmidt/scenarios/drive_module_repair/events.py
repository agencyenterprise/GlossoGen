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


class DriveModuleModuleSpec(BaseModel):
    """One unit's full service-spec sheet this round (per-unit dynamic specs)."""

    module_label: str
    specs: list[DriveModuleSpecEntry]


class DriveModuleModuleFaultTree(BaseModel):
    """One unit's symptom -> component fault-tree this round (per-unit dynamic)."""

    module_label: str
    entries: list[DriveModuleFaultEntry]


class DriveModuleCaseStarted(EventBase):
    """Emitted once at round start with the full ground-truth case.

    ``module_fault_trees`` is the per-unit symptom -> component mapping (held by
    the diagnostics engineer; each unit is a different revision).
    ``module_spec_tables`` is the per-unit component -> tool/torque/calibration
    mapping (held by the spec engineer). ``stages`` is the derived ordered
    ground truth: units in canonical order, components within each in
    access-depth order. Faults are revealed to the technician one at a time at
    runtime, and each unit's fault-tree + spec sheet are pushed to the engineers
    only when that unit is reached, so the full case here is the ground truth,
    not what any agent sees up front.
    """

    event_type: Literal["drive_module_case_started"] = "drive_module_case_started"
    case_number: int
    module_count: int
    replacement_count: int
    module_fault_trees: list[DriveModuleModuleFaultTree]
    module_spec_tables: list[DriveModuleModuleSpec]
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
