"""Per-round and postmortem prompt injections for the drive_module_repair scenario.

Each round every agent receives a role-specific injection: the field
technician sees the diagnostic panel (the observed symptoms), the diagnostics
engineer sees this round's fault-tree (symptom -> component), and the spec
engineer sees this round's service-spec table (component -> tool / torque /
calibration). The helpers here pick the right template per role.
"""

from schmidt.scenarios.drive_module_repair.drive_module_cases import DriveModuleCase
from schmidt.scenarios.drive_module_repair.ids import (
    DIAGNOSTICS_ENGINEER_ID,
    DIAGNOSTICS_ENGINEER_INJECTION_TEMPLATE,
    FIELD_TECHNICIAN_ID,
    FIELD_TECHNICIAN_INJECTION_TEMPLATE,
    SPEC_ENGINEER_ID,
    SPEC_ENGINEER_INJECTION_TEMPLATE,
)
from schmidt.scenarios.drive_module_repair.world_state import DriveModuleOutcome
from schmidt.template_renderer import TemplateRenderer

_INJECTION_TEMPLATE_BY_AGENT = {
    FIELD_TECHNICIAN_ID: FIELD_TECHNICIAN_INJECTION_TEMPLATE,
    DIAGNOSTICS_ENGINEER_ID: DIAGNOSTICS_ENGINEER_INJECTION_TEMPLATE,
    SPEC_ENGINEER_ID: SPEC_ENGINEER_INJECTION_TEMPLATE,
}


def render_round_injection(
    round_number: int,
    agent_id: str,
    case: DriveModuleCase,
    previous_outcome: DriveModuleOutcome | None,
    renderer: TemplateRenderer,
) -> str | None:
    """Return the per-round injection for one agent, or None for unknown agents."""
    template_name = _INJECTION_TEMPLATE_BY_AGENT.get(agent_id)
    if template_name is None:
        return None
    rendered = renderer.render(
        template_name=template_name,
        template_variables={
            "round_number": round_number,
            "current_case": case,
            "previous_outcome": previous_outcome,
        },
    )
    if not rendered:
        return None
    return rendered


def render_postmortem_injection(
    round_number: int,
    previous_outcome: DriveModuleOutcome | None,
    renderer: TemplateRenderer,
) -> str | None:
    """Render the postmortem injection summarising the previous round."""
    rendered = renderer.render(
        template_name="postmortem_injection.jinja",
        template_variables={
            "round_number": round_number,
            "previous_outcome": previous_outcome,
        },
    )
    if not rendered:
        return None
    return rendered
