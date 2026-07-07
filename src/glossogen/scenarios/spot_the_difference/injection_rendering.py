"""Per-round and postmortem prompt injections for the spot_the_difference scenario.

Each round, both viewers on a team receive a Jinja-rendered injection that
shows only *their* scene's objects (left viewer = scene A, right viewer =
scene B), rendered relationally (region + relations to other objects, never
exact coordinates), the number of differences to find, the character budget
(only when one is set), and the previous round's result. Neither viewer's
injection ever contains the other scene or the planted differences.
"""

from glossogen.scenarios.spot_the_difference.ids import (
    SCENE_SIDE_LEFT,
    VIEWER_LEFT_INJECTION_TEMPLATE,
    VIEWER_RIGHT_INJECTION_TEMPLATE,
)
from glossogen.scenarios.spot_the_difference.scene_generation import (
    DiffCase,
    render_scene_relational,
)
from glossogen.scenarios.spot_the_difference.team_routing import (
    AGENT_ID_TO_SCENE_SIDE,
    scene_side_for_agent,
)
from glossogen.scenarios.spot_the_difference.world_state import DiffOutcome
from glossogen.template_renderer import TemplateRenderer


def render_round_injection(
    round_number: int,
    agent_id: str,
    case: DiffCase,
    previous_outcome: DiffOutcome | None,
    two_teams: bool,
    renderer: TemplateRenderer,
) -> str | None:
    """Return the per-round injection for one viewer, or None for non-viewers."""
    if agent_id not in AGENT_ID_TO_SCENE_SIDE:
        return None
    scene_side = scene_side_for_agent(agent_id=agent_id)
    if scene_side == SCENE_SIDE_LEFT:
        template_name = VIEWER_LEFT_INJECTION_TEMPLATE
        my_scene = case.scene_a
    else:
        template_name = VIEWER_RIGHT_INJECTION_TEMPLATE
        my_scene = case.scene_b
    rendered = renderer.render(
        template_name=template_name,
        template_variables={
            "round_number": round_number,
            "difference_count": case.difference_count,
            "round_time_budget_seconds": case.round_time_budget_seconds,
            "my_objects": render_scene_relational(scene=my_scene, grid_size=case.grid_size),
            "previous_outcome": previous_outcome,
            "two_teams": two_teams,
        },
    )
    if not rendered:
        return None
    return rendered


def render_postmortem_injection(
    round_number: int,
    previous_outcome: DiffOutcome | None,
    two_teams: bool,
    renderer: TemplateRenderer,
) -> str | None:
    """Render the postmortem injection for one team's discussion channel."""
    rendered = renderer.render(
        template_name="postmortem_injection.jinja",
        template_variables={
            "round_number": round_number,
            "previous_outcome": previous_outcome,
            "two_teams": two_teams,
        },
    )
    if not rendered:
        return None
    return rendered
