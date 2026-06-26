"""Adapter that turns a ``DriveModuleCase`` namedtuple into the event-log model.

The scenario keeps its ground truth as plain ``NamedTuple`` instances (see
:mod:`drive_module_cases`); the event log serializes round-start state as the
``DriveModuleCaseStarted`` Pydantic model (see :mod:`events`). This helper
bridges the two whenever the scenario emits the case-started event.
"""

from schmidt.scenarios.drive_module_repair.drive_module_cases import DriveModuleCase
from schmidt.scenarios.drive_module_repair.events import (
    DriveModuleCaseStarted,
    DriveModuleFaultEntry,
    DriveModuleSpecEntry,
    DriveModuleStage,
)


def case_started_event(round_number: int, case: DriveModuleCase) -> DriveModuleCaseStarted:
    """Build the full ``DriveModuleCaseStarted`` event for ``case`` at ``round_number``."""
    return DriveModuleCaseStarted(
        round_number=round_number,
        case_number=case.case_number,
        replacement_count=case.replacement_count,
        panel_symptoms=list(case.panel_symptoms),
        fault_tree=[
            DriveModuleFaultEntry(symptom=symptom, component=component)
            for symptom, component in case.fault_tree
        ],
        spec_table=[
            DriveModuleSpecEntry(
                component=spec.component,
                tool=spec.tool,
                torque_nm=spec.torque_nm,
                calibration=spec.calibration,
            )
            for spec in case.spec_table
        ],
        stages=[
            DriveModuleStage(
                step_index=stage.step_index,
                component=stage.component,
                symptom=stage.symptom,
                tool=stage.tool,
                torque_nm=stage.torque_nm,
                calibration=stage.calibration,
                access_depth=stage.access_depth,
                judge_expected_action=stage.judge_expected_action,
            )
            for stage in case.stages
        ],
        round_time_budget_seconds=case.round_time_budget_seconds,
    )
