"""Per-scenario :class:`ScenarioExportSpec` instances for the run-context scan.

Maps a scenario name to the event types, primary channel ids, per-stage field
names, and agent roles the shared JSONL scan needs. ``get_export_spec`` resolves
the ``--scenario`` flag of every exporter to one of these.
"""

from analysis.run_export.run_context_scan import RoleSpec, ScenarioExportSpec
from schmidt.scenarios.drive_module_repair.ids import (
    BAY_CHANNEL_ID,
    DIAGNOSTICS_ENGINEER_ID,
    FIELD_TECHNICIAN_ID,
    SPEC_ENGINEER_ID,
)
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_ID,
    LINK_CHANNEL_IDS,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_B_ID,
    STABILIZATION_ENGINEER_ID,
)

VEYRU_SPEC = ScenarioExportSpec(
    scenario_name="veyru",
    primary_channel_ids=LINK_CHANNEL_IDS,
    case_event_type="veyru_case_started",
    stage_symptoms_field="observable_symptoms",
    stage_actions_field="judge_expected_actions",
    judged_event_type="veyru_stabilization_judged",
    roles=(
        RoleSpec(
            role="field_observer",
            agent_ids=frozenset({FIELD_OBSERVER_ID, OBSERVER_A_ID, OBSERVER_B_ID}),
            model_column="field_observer_model",
            event_column="field_observer_round_event",
        ),
        # "specialist" is a legacy agent_id some early runs used for the engineer role.
        RoleSpec(
            role="stabilization_engineer",
            agent_ids=frozenset(
                {
                    STABILIZATION_ENGINEER_ID,
                    STABILIZATION_ENGINEER_A_ID,
                    STABILIZATION_ENGINEER_B_ID,
                    "specialist",
                }
            ),
            model_column="engineer_model",
            event_column="engineer_round_event",
        ),
    ),
)

DRIVE_MODULE_REPAIR_SPEC = ScenarioExportSpec(
    scenario_name="drive_module_repair",
    primary_channel_ids=frozenset({BAY_CHANNEL_ID}),
    case_event_type="drive_module_case_started",
    stage_symptoms_field="symptom",
    stage_actions_field="judge_expected_action",
    judged_event_type="drive_module_replacement_judged",
    roles=(
        RoleSpec(
            role="field_technician",
            agent_ids=frozenset({FIELD_TECHNICIAN_ID}),
            model_column="field_technician_model",
            event_column="field_technician_round_event",
        ),
        RoleSpec(
            role="diagnostics_engineer",
            agent_ids=frozenset({DIAGNOSTICS_ENGINEER_ID}),
            model_column="diagnostics_engineer_model",
            event_column="diagnostics_engineer_round_event",
        ),
        RoleSpec(
            role="spec_engineer",
            agent_ids=frozenset({SPEC_ENGINEER_ID}),
            model_column="spec_engineer_model",
            event_column="spec_engineer_round_event",
        ),
    ),
)

_SPECS_BY_SCENARIO = {spec.scenario_name: spec for spec in (VEYRU_SPEC, DRIVE_MODULE_REPAIR_SPEC)}


def get_export_spec(scenario_name: str) -> ScenarioExportSpec:
    """Return the export spec for ``scenario_name`` or raise ``KeyError`` with the known set."""
    spec = _SPECS_BY_SCENARIO.get(scenario_name)
    if spec is None:
        known = ", ".join(sorted(_SPECS_BY_SCENARIO))
        raise KeyError(f"No export spec for scenario '{scenario_name}'. Known scenarios: {known}.")
    return spec
