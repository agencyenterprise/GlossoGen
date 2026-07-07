"""Per-round and postmortem prompt injections for the spillway scenario.

Each round, every agent receives a Jinja-rendered injection: the dam
operator gets the gauge reading, civil defense gets the weather forecast and
inflow, and the park ranger gets the park schedule. All three also receive
the shared current time. The helpers here compute the human-readable time
and park-status labels and pick the right template per role.
"""

from glossogen.scenarios.spillway_release.ids import (
    CIVIL_DEFENSE_ID,
    CIVIL_DEFENSE_INJECTION_TEMPLATE,
    DAM_OPERATOR_ID,
    DAM_OPERATOR_INJECTION_TEMPLATE,
    PARK_RANGER_ID,
    PARK_RANGER_INJECTION_TEMPLATE,
)
from glossogen.scenarios.spillway_release.spillway_cases import SpillwayCase, format_hours
from glossogen.scenarios.spillway_release.world_state import SpillwayOutcome
from glossogen.template_renderer import TemplateRenderer

_INJECTION_TEMPLATE_BY_AGENT = {
    DAM_OPERATOR_ID: DAM_OPERATOR_INJECTION_TEMPLATE,
    CIVIL_DEFENSE_ID: CIVIL_DEFENSE_INJECTION_TEMPLATE,
    PARK_RANGER_ID: PARK_RANGER_INJECTION_TEMPLATE,
}


def park_status_label(case: SpillwayCase) -> str:
    """Build the ranger-facing description of the park schedule and lockability."""
    if case.park_opens_at_hours is None:
        occupancy = "The park is CLOSED all day; no visitors will be downstream."
    elif case.park_opens_at_hours <= case.current_time_hours:
        occupancy = (
            f"The park is OPEN now (opened at {format_hours(value=case.park_opens_at_hours)}); "
            f"about {case.visitors} visitors are on the downstream trails."
        )
    else:
        occupancy = (
            f"The park is CLOSED now but scheduled to OPEN at "
            f"{format_hours(value=case.park_opens_at_hours)}; "
            f"about {case.visitors} visitors are expected then."
        )
    if case.park_lockable:
        lockability = "You may close it now or keep it closed past its opening time."
    else:
        lockability = (
            "A committed event is booked today, so you CANNOT close it — only a "
            "civil-defense evacuation can clear the area for a release."
        )
    return f"{occupancy} {lockability}"


def render_round_injection(
    round_number: int,
    agent_id: str,
    case: SpillwayCase,
    previous_outcome: SpillwayOutcome | None,
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
            "current_time_label": format_hours(value=case.current_time_hours),
            "day_end_label": format_hours(value=case.day_end_hours),
            "park_status_label": park_status_label(case=case),
        },
    )
    if not rendered:
        return None
    return rendered


def render_postmortem_injection(
    round_number: int,
    previous_outcome: SpillwayOutcome | None,
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
