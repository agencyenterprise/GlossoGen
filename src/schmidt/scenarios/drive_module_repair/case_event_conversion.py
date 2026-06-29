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
    DriveModuleModuleFaultTree,
    DriveModuleModuleSpec,
    DriveModuleSpecEntry,
    DriveModuleStage,
)


def case_started_event(round_number: int, case: DriveModuleCase) -> DriveModuleCaseStarted:
    """Build the full ``DriveModuleCaseStarted`` event for ``case`` at ``round_number``."""
    return DriveModuleCaseStarted(
        round_number=round_number,
        case_number=case.case_number,
        module_count=case.module_count,
        replacement_count=case.total_replacement_count,
        module_fault_trees=[
            DriveModuleModuleFaultTree(
                module_label=tree.module_label,
                entries=[
                    DriveModuleFaultEntry(symptom=symptom, component=component)
                    for symptom, component in tree.entries
                ],
            )
            for tree in case.module_fault_trees
        ],
        module_spec_tables=[
            DriveModuleModuleSpec(
                module_label=table.module_label,
                specs=[
                    DriveModuleSpecEntry(
                        component=spec.component,
                        service_class=spec.service_class,
                        tool=spec.tool,
                        torque_nm=spec.torque_nm,
                        passes=spec.passes,
                        calibration=spec.calibration,
                        steps=list(spec.steps),
                    )
                    for spec in table.specs
                ],
            )
            for table in case.module_spec_tables
        ],
        stages=[
            DriveModuleStage(
                step_index=stage.step_index,
                module_label=stage.module_label,
                component=stage.component,
                symptom=stage.symptom,
                service_class=stage.service_class,
                tool=stage.tool,
                torque_nm=stage.torque_nm,
                passes=stage.passes,
                calibration=stage.calibration,
                steps=list(stage.steps),
                access_depth=stage.access_depth,
                judge_expected_action=stage.judge_expected_action,
            )
            for stage in case.stages
        ],
        round_time_budget_seconds=case.round_time_budget_seconds,
    )
