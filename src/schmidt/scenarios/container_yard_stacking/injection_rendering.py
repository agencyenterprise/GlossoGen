"""Per-round and postmortem prompt injections for the yard scenario.

Each round, every active agent receives a Jinja-rendered injection that
describes the new yard case (or, for postmortem rounds, the previous
round's outcome). The functions here pick the right template for each
role, gate the intern's lifecycle (silent observation → takeover), and
hand variables to the renderer.
"""

from schmidt.scenarios.container_yard_stacking.case_rendering import render_container
from schmidt.scenarios.container_yard_stacking.ids import (
    CRANE_OPERATOR_INJECTION_TEMPLATE,
    INTERN_ID,
    INTERN_INJECTION_TEMPLATE,
    LOGISTICS_PLANNER_INJECTION_TEMPLATE,
    YARD_OPERATOR_INJECTION_TEMPLATE,
)
from schmidt.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from schmidt.scenarios.container_yard_stacking.team_routing import (
    AGENT_ID_TO_ROLE_KIND,
    team_id_for_agent,
)
from schmidt.scenarios.container_yard_stacking.world_state import YardOutcome
from schmidt.scenarios.container_yard_stacking.yard_cases import YardCase
from schmidt.template_renderer import TemplateRenderer


def render_round_injection(
    round_number: int,
    agent_id: str,
    knobs: ContainerYardStackingKnobs,
    case: YardCase,
    previous_outcome: YardOutcome | None,
    renderer: TemplateRenderer,
) -> str | None:
    """Return the per-round injection for one agent, or None."""
    role_kind = AGENT_ID_TO_ROLE_KIND.get(agent_id)
    if role_kind is None:
        return None
    if agent_id == INTERN_ID and not intern_should_be_active(
        round_number=round_number, knobs=knobs
    ):
        return None
    template_name = _injection_template_for_role(role_kind=role_kind)
    team_id = team_id_for_agent(agent_id=agent_id)
    spotter_lines = [
        (render_container(container=step.container), step.intake_slot)
        for step in sorted(case.steps, key=lambda s: s.intake_slot)
    ]
    planner_lines = [
        (render_container(container=step.container), step.target_slot)
        for step in sorted(case.steps, key=lambda s: s.target_slot)
    ]
    crane_occupancy = [
        (slot, "FULL" if case.initial_row[slot] is not None else "EMPTY")
        for slot in range(1, case.yard_slot_count + 1)
    ]
    rendered = renderer.render(
        template_name=template_name,
        template_variables={
            "round_number": round_number,
            "current_case": case,
            "spotter_lines": spotter_lines,
            "planner_lines": planner_lines,
            "crane_occupancy": crane_occupancy,
            "previous_outcome": previous_outcome,
            "knobs": knobs,
            "team_id": team_id,
            "intern_join_round": knobs.intern_join_round,
            "intern_takeover_round": knobs.intern_takeover_round,
            "intern_active": intern_has_taken_over(round_number=round_number, knobs=knobs),
        },
    )
    if not rendered:
        return None
    return rendered


def render_postmortem_injection(
    round_number: int,
    agent_id: str,
    previous_outcome: YardOutcome | None,
    renderer: TemplateRenderer,
) -> str | None:
    """Render the postmortem injection for one agent's discussion channel."""
    team_id = team_id_for_agent(agent_id=agent_id)
    rendered = renderer.render(
        template_name="postmortem_injection.jinja",
        template_variables={
            "round_number": round_number,
            "previous_outcome": previous_outcome,
            "team_id": team_id,
        },
    )
    if not rendered:
        return None
    return rendered


def _injection_template_for_role(role_kind: str) -> str:
    """Map the role kind to its injection template filename."""
    if role_kind == "yard_operator":
        return YARD_OPERATOR_INJECTION_TEMPLATE
    if role_kind == "logistics_planner":
        return LOGISTICS_PLANNER_INJECTION_TEMPLATE
    if role_kind == "intern":
        return INTERN_INJECTION_TEMPLATE
    return CRANE_OPERATOR_INJECTION_TEMPLATE


def intern_should_be_active(round_number: int, knobs: ContainerYardStackingKnobs) -> bool:
    """Whether the intern should receive injections this round (joined and not retired)."""
    if not knobs.intern_enabled:
        return False
    if knobs.intern_join_round is None:
        return False
    return round_number >= knobs.intern_join_round


def intern_has_taken_over(round_number: int, knobs: ContainerYardStackingKnobs) -> bool:
    """Whether the intern is now the active crane operator."""
    if not knobs.intern_enabled:
        return False
    if knobs.intern_takeover_round is None:
        return False
    return round_number >= knobs.intern_takeover_round
