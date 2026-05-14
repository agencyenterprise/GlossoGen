"""Per-round and postmortem prompt injections for the veyru scenario.

Each round, every active agent receives a Jinja-rendered injection that
describes the new Veyru case (or, for the postmortem phase, the previous
round's outcome). The helpers here pick the right template for each
role, gate the intern's lifecycle (silent observation → takeover) and
the observer swap (suppress prior-round context for a newly-swapped
agent), and hand variables to the renderer.
"""

import logging

from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_ID,
    FIELD_OBSERVER_INJECTION_TEMPLATE,
    INTERN_ID,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_B_ID,
    STABILIZATION_ENGINEER_ID,
    STABILIZATION_ENGINEER_INJECTION_TEMPLATE,
    TEAM_SOLO_ID,
)
from schmidt.scenarios.veyru.knobs import VeyruKnobs
from schmidt.scenarios.veyru.veyru_cases import VeyruCase, get_stellar_treatment_mapping
from schmidt.scenarios.veyru.world import VeyruWorld
from schmidt.scenarios.veyru.world_state import VeyruOutcome
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


def intern_has_taken_over(world: VeyruWorld, knobs: VeyruKnobs) -> bool:
    """Whether the intern has been promoted to field observer."""
    if not knobs.intern_enabled:
        return False
    if TEAM_SOLO_ID not in world.teams:
        return False
    return world.teams[TEAM_SOLO_ID].current_observer_id == INTERN_ID


def is_intern_in_observer_state(
    world: VeyruWorld, knobs: VeyruKnobs, current_round: int | None
) -> bool:
    """Whether the intern has joined the link channel but has not yet taken over."""
    if not knobs.intern_enabled:
        return False
    if knobs.intern_join_round is None:
        return False
    if current_round is None:
        return False
    if current_round < knobs.intern_join_round:
        return False
    return not intern_has_taken_over(world=world, knobs=knobs)


def is_observer_agent(agent_id: str, world: VeyruWorld, knobs: VeyruKnobs) -> bool:
    """Whether this agent is acting as a field observer in the current round."""
    if agent_id in (OBSERVER_A_ID, OBSERVER_B_ID):
        return True
    if agent_id == FIELD_OBSERVER_ID:
        return not intern_has_taken_over(world=world, knobs=knobs)
    if agent_id == INTERN_ID:
        return intern_has_taken_over(world=world, knobs=knobs)
    return False


def previous_outcome_for_agent(
    world: VeyruWorld,
    agent_id: str,
    round_number: int,
) -> VeyruOutcome | None:
    """Return the most recent outcome for the team the agent belongs to.

    Returns None for an agent that was just swapped in at the start of
    ``round_number`` — they did not participate in ``round_number - 1``
    and the ``PREVIOUS VEYRU RESULT`` block would leak prior-round
    context they should not see.
    """
    if world.was_agent_just_swapped_in_round(agent_id=agent_id, round_number=round_number):
        return None
    team_id = world.get_team_for_agent(agent_id=agent_id)
    outcomes = world.get_outcomes_for_team(team_id=team_id)
    if len(outcomes) == 0:
        return None
    return outcomes[-1]


def partner_display_name(
    world: VeyruWorld, agent_id: str, agent_display_names: dict[str, str]
) -> str:
    """Return the display name of the agent's current partner on their team."""
    team_id = world.get_team_for_agent(agent_id=agent_id)
    team = world.teams[team_id]
    if agent_id == team.current_observer_id:
        partner_id = team.stabilization_engineer_id
    else:
        partner_id = team.current_observer_id
    return agent_display_names.get(partner_id, partner_id)


def render_round_injection(
    round_number: int,
    agent_id: str,
    knobs: VeyruKnobs,
    veyru_cases: list[VeyruCase],
    world: VeyruWorld,
    agent_display_names: dict[str, str],
    renderer: TemplateRenderer,
) -> str | None:
    """Return the per-round injection for one agent, or None."""
    if agent_id == INTERN_ID and not intern_has_taken_over(world=world, knobs=knobs):
        return None
    if (
        knobs.intern_enabled
        and agent_id == FIELD_OBSERVER_ID
        and intern_has_taken_over(world=world, knobs=knobs)
    ):
        return None

    if is_observer_agent(agent_id=agent_id, world=world, knobs=knobs):
        template_name: str | None = FIELD_OBSERVER_INJECTION_TEMPLATE
    elif agent_id in (
        STABILIZATION_ENGINEER_ID,
        STABILIZATION_ENGINEER_A_ID,
        STABILIZATION_ENGINEER_B_ID,
    ):
        template_name = STABILIZATION_ENGINEER_INJECTION_TEMPLATE
    else:
        template_name = None
    if template_name is None:
        return None

    current_case_index = (round_number - 1) % len(veyru_cases)
    current_case = veyru_cases[current_case_index]
    previous_outcome = previous_outcome_for_agent(
        world=world,
        agent_id=agent_id,
        round_number=round_number,
    )
    treatment_mapping = get_stellar_treatment_mapping(
        stellar_reading=current_case.stellar_reading,
    )
    swap_just_happened = world.peek_swap_just_happened()
    partner = partner_display_name(
        world=world, agent_id=agent_id, agent_display_names=agent_display_names
    )
    intern_takeover_just_happened = agent_id == INTERN_ID and world.peek_intern_takeover()

    rendered = renderer.render(
        template_name=template_name,
        template_variables={
            "round_number": round_number,
            "current_case": current_case,
            "first_stage_symptoms": current_case.stages[0].observable_symptoms,
            "previous_outcome": previous_outcome,
            "knobs": knobs,
            "treatment_mapping": treatment_mapping,
            "swap_just_happened": swap_just_happened,
            "announce_swap": knobs.announce_swap,
            "partner_display_name": partner,
            "intern_takeover_just_happened": intern_takeover_just_happened,
            "intern_join_round": knobs.intern_join_round,
        },
    )
    if not rendered:
        return None
    logger.debug(
        "Injection for agent %s at round %d: %d chars",
        agent_id,
        round_number,
        len(rendered),
    )
    return rendered


def render_postmortem_injection(
    round_number: int,
    agent_id: str,
    knobs: VeyruKnobs,
    world: VeyruWorld,
    renderer: TemplateRenderer,
) -> str | None:
    """Return postmortem injection when postmortem is enabled, None otherwise."""
    if not knobs.postmortem_enabled:
        return None
    if world.is_postmortem_disabled:
        return None
    if knobs.intern_enabled:
        if agent_id == INTERN_ID and not intern_has_taken_over(world=world, knobs=knobs):
            return None
        if agent_id == FIELD_OBSERVER_ID and intern_has_taken_over(world=world, knobs=knobs):
            return None

    team_id = world.get_team_for_agent(agent_id=agent_id)
    outcome = world.compute_outcome_if_needed(
        round_number=round_number,
        team_id=team_id,
    )

    rendered = renderer.render(
        template_name="postmortem_injection.jinja",
        template_variables={
            "round_number": round_number,
            "previous_outcome": outcome,
        },
    )
    if not rendered:
        return None
    logger.debug(
        "Postmortem injection for agent %s at round %d: %d chars",
        agent_id,
        round_number,
        len(rendered),
    )
    return rendered
