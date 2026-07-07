"""Mutable per-team state and immutable outcome types for the veyru world.

The world holds one ``TeamState`` per team (solo mode keeps one; two-team
mode keeps two). Each ``TeamState`` tracks per-round character usage,
stabilization progress, the rolling list of historical outcomes, and a
mutable ``current_observer_id`` (swap and intern takeover both rewire
this).
"""

from typing import NamedTuple

from glossogen.scenarios.veyru.ids import TeamId


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
    (possibly swappable) field observer. Per-round character usage,
    stabilization progress, and historical outcomes are all team-scoped.
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
        self.current_round_characters: int = 0
        self.veyru_alive: bool = True
        self.veyru_stabilized: bool = False
        self.notified_thresholds: set[str] = set()
        self.current_stage_index: int = 0
        self.stage_outcomes: list[StageOutcome] = []
        self.outcomes: list[VeyruOutcome] = []

    def reset_for_new_round(self) -> None:
        """Clear per-round counters before a fresh case is loaded."""
        self.current_round_characters = 0
        self.veyru_alive = True
        self.veyru_stabilized = False
        self.notified_thresholds = set()
        self.current_stage_index = 0
        self.stage_outcomes = []
