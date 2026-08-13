"""Mutable per-team state and immutable outcome types for the veyru world.

The world holds one ``TeamState`` per team (solo mode keeps one; two-team
mode keeps two). Each ``TeamState`` tracks per-round character usage,
stabilization progress, the rolling list of historical outcomes, and a
mutable ``current_observer_id`` (swap and intern takeover both rewire
this).
"""

from typing import NamedTuple

from glossogen.engine.team_declaration import Debrief, TeamSpec
from glossogen.scenarios.veyru.ids import (
    FIELD_OBSERVER_SYSTEM_TEMPLATE,
    STABILIZATION_ENGINEER_SYSTEM_TEMPLATE,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TeamId,
)

# veyru's own ids, by the name the declaration carries them under.
TEAM_IDS_BY_NAME: dict[str, TeamId] = {
    TEAM_SOLO_ID: TEAM_SOLO_ID,
    TEAM_A_ID: TEAM_A_ID,
    TEAM_B_ID: TEAM_B_ID,
}


class StageOutcome(NamedTuple):
    """Result of a single stage within a composite case."""

    motif_name: str
    stabilized: bool


class VeyruOutcome(NamedTuple):
    """Result of a single Veyru case after a round completes."""

    team_id: TeamId
    case_number: int
    failure_name: str
    stabilized: bool
    characters_used: int
    time_elapsed_seconds: float
    time_budget_seconds: int
    stages_completed: int
    total_stages: int
    stage_outcomes: tuple[StageOutcome, ...]


class TeamState:
    """Mutable per-team state tracked by the Veyru world.

    A team owns a communication channel, a stabilization engineer, and a
    (possibly swappable) field observer. Stabilization progress is team-scoped
    here; the per-round character count is metered by the engine's
    ``RoundWorld`` and finished rounds are kept in its ``RoundOutcomeLog``.
    """

    def __init__(
        self,
        team_id: TeamId,
        current_observer_id: str,
        stabilization_engineer_id: str,
        link_channel_id: str,
        postmortem_channel_id: str | None,
    ) -> None:
        self.team_id = team_id
        self.current_observer_id = current_observer_id
        self.stabilization_engineer_id = stabilization_engineer_id
        self.link_channel_id = link_channel_id
        self.postmortem_channel_id = postmortem_channel_id
        self.veyru_alive: bool = True
        self.veyru_stabilized: bool = False
        self.current_stage_index: int = 0
        self.stage_outcomes: list[StageOutcome] = []

    def reset_for_new_round(self) -> None:
        """Clear per-round counters before a fresh case is loaded."""
        self.veyru_alive = True
        self.veyru_stabilized = False
        self.current_stage_index = 0
        self.stage_outcomes = []


def build_team_states(team_specs: tuple[TeamSpec, ...]) -> dict[TeamId, TeamState]:
    """Build one ``TeamState`` per declared team.

    The declaration already says which channel a team talks on, which it
    debriefs on, and who sits in it. Reading the state off it is what keeps the
    two from drifting: the ids are named once, in ``team_declaration``.

    A team's own id is narrowed back to veyru's ``TeamId`` here, against the
    literals veyru declared, so an id veyru does not know fails loudly at
    construction rather than silently missing a lookup later.
    """
    states: dict[TeamId, TeamState] = {}
    for spec in team_specs:
        team_id = TEAM_IDS_BY_NAME[spec.team_id]
        if isinstance(spec.debrief, Debrief):
            postmortem_channel_id: str | None = spec.debrief.channel_id
        else:
            postmortem_channel_id = None
        states[team_id] = TeamState(
            team_id=team_id,
            current_observer_id=_role_with(spec=spec, template=FIELD_OBSERVER_SYSTEM_TEMPLATE),
            stabilization_engineer_id=_role_with(
                spec=spec, template=STABILIZATION_ENGINEER_SYSTEM_TEMPLATE
            ),
            link_channel_id=spec.task.channel_id,
            postmortem_channel_id=postmortem_channel_id,
        )
    return states


def _role_with(spec: TeamSpec, template: str) -> str:
    """Return the agent filling the seat that renders ``template``."""
    for role in spec.roles:
        if role.system_template == template:
            return role.agent_id
    raise AssertionError(f"team {spec.team_id} declares no role rendering {template}")
