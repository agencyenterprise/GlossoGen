"""Per-round and debrief prompt injections for the orbital_anomaly scenario.

Each round, every agent receives a Jinja-rendered injection carrying only
its own view of the new anomaly: the astronaut gets the cockpit alarm and
panel observation, the telemetry officer gets the telemetry readout, and
the systems engineer gets the rotated configuration table.
"""

from schmidt.scenarios.orbital_anomaly.ids import (
    ASTRONAUT_ID,
    ASTRONAUT_INJECTION_TEMPLATE,
    SYSTEMS_ENGINEER_ID,
    SYSTEMS_ENGINEER_INJECTION_TEMPLATE,
    TELEMETRY_OFFICER_ID,
    TELEMETRY_OFFICER_INJECTION_TEMPLATE,
)
from schmidt.scenarios.orbital_anomaly.orbital_anomaly_cases import get_config_variant_mapping
from schmidt.scenarios.orbital_anomaly.world import OrbitalAnomalyWorld
from schmidt.template_renderer import TemplateRenderer

_INJECTION_TEMPLATE_BY_AGENT: dict[str, str] = {
    ASTRONAUT_ID: ASTRONAUT_INJECTION_TEMPLATE,
    TELEMETRY_OFFICER_ID: TELEMETRY_OFFICER_INJECTION_TEMPLATE,
    SYSTEMS_ENGINEER_ID: SYSTEMS_ENGINEER_INJECTION_TEMPLATE,
}


def render_round_injection(
    round_number: int,
    agent_id: str,
    world: OrbitalAnomalyWorld,
    renderer: TemplateRenderer,
) -> str | None:
    """Return the per-round injection for one agent, or None."""
    template_name = _INJECTION_TEMPLATE_BY_AGENT.get(agent_id)
    if template_name is None:
        return None
    case = world.current_case
    if case is None:
        return None
    first_stage = case.stages[0]
    rendered = renderer.render(
        template_name=template_name,
        template_variables={
            "round_number": round_number,
            "current_case": case,
            "previous_outcome": world.previous_outcome(),
            "first_stage_cockpit_alarm": first_stage.cockpit_alarm,
            "first_stage_panel_observation": first_stage.panel_observation,
            "first_stage_telemetry_readout": first_stage.telemetry_readout,
            "config_mapping": get_config_variant_mapping(variant_index=case.variant_index),
        },
    )
    if not rendered:
        return None
    return rendered


def render_postmortem_injection(
    round_number: int,
    world: OrbitalAnomalyWorld,
    renderer: TemplateRenderer,
) -> str | None:
    """Render the debrief injection shown to every agent after a round."""
    rendered = renderer.render(
        template_name="postmortem_injection.jinja",
        template_variables={
            "round_number": round_number,
            "previous_outcome": world.previous_outcome(),
        },
    )
    if not rendered:
        return None
    return rendered
