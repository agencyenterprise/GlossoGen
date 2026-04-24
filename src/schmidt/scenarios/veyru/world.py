"""World simulation for the Veyru stabilization scenario.

Monitors cumulative communication character usage per team per round and
sends real-time Veyru status notifications when time thresholds are crossed.
A team's Veyru collapses when its total communication time exceeds the case's
time budget. A Veyru is stabilized only when the team's current field
observer calls ``stabilize_veyru`` with an action that the LLM judge deems
adequate.

The world is always keyed by team. In single-team mode, there is one team
keyed ``"solo"``. In two-team mode, teams ``"a"`` and ``"b"`` run in parallel
on identical cases, with fully isolated communication channels. When the
observer swap fires, the ``current_observer_id`` on each team is updated so
stabilization calls and threshold notifications route to the new pairing.
"""

import asyncio
import logging
from typing import NamedTuple

from schmidt.runtime.scenario_world import (
    MessageEvent,
    RoundAdvancedEvent,
    ScenarioWorld,
    WorldContext,
)
from schmidt.scenarios.veyru.ids import (
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    VEYRU_COLLAPSED_MARKER,
    VEYRU_STABILIZED_MARKER,
    TeamId,
)
from schmidt.scenarios.veyru.veyru_cases import VeyruCase, VeyruStage

logger = logging.getLogger(__name__)

THRESHOLD_COLLAPSED = "collapsed"
THRESHOLD_CRITICAL = "critical"


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

    A team owns a communication channel, a stabilization engineer, and a (possibly
    swappable) field observer. Per-round character usage, stabilization
    progress, and historical outcomes are all team-scoped.
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


class VeyruWorld(ScenarioWorld):
    """Monitors communication and pushes real-time Veyru status updates per team.

    Tracks cumulative character count per round per team. When a team's
    simulated time crosses 75% of the Veyru's budget or the budget is
    exceeded, broadcasts a critical or collapse notification to that team's
    comm link only. A Veyru survives only if the team's current field
    observer calls ``stabilize_veyru`` with a correct action before time
    runs out.
    """

    _context: WorldContext

    def __init__(
        self,
        veyru_cases: list[VeyruCase],
        teams: dict[TeamId, TeamState],
    ) -> None:
        self._veyru_cases = veyru_cases
        self._teams = teams
        self._current_case: VeyruCase | None = None
        self._in_postmortem: bool = False
        self._postmortem_globally_disabled: bool = False
        self._swap_just_happened: bool = False
        self._intern_takeover_just_happened: bool = False
        self._channels_by_team: dict[str, TeamId] = self._build_channel_to_team_lookup(
            teams=teams,
        )

    @staticmethod
    def _build_channel_to_team_lookup(
        teams: dict[TeamId, TeamState],
    ) -> dict[str, TeamId]:
        """Reverse-index from channel ID to team ID for message routing."""
        lookup: dict[str, TeamId] = {}
        for team_id, state in teams.items():
            lookup[state.link_channel_id] = team_id
        return lookup

    @property
    def teams(self) -> dict[TeamId, TeamState]:
        """Return the teams managed by this world."""
        return self._teams

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def current_case(self) -> VeyruCase | None:
        """The Veyru case for the current round (shared across teams)."""
        return self._current_case

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is in a postmortem discussion phase."""
        return self._in_postmortem

    @property
    def is_postmortem_disabled(self) -> bool:
        """Whether postmortem has been globally disabled (e.g. post-swap)."""
        return self._postmortem_globally_disabled

    def enter_postmortem(self) -> None:
        """Mark the start of a postmortem discussion phase."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Mark the end of a postmortem discussion phase."""
        self._in_postmortem = False

    def disable_postmortem_globally(self) -> None:
        """Close the postmortem channel for the rest of the simulation."""
        self._postmortem_globally_disabled = True

    def mark_swap_just_happened(self) -> None:
        """Flag that a swap just fired; consumed by the next injection pass."""
        self._swap_just_happened = True

    def consume_swap_just_happened(self) -> bool:
        """Return whether a swap just happened and clear the flag."""
        was_set = self._swap_just_happened
        self._swap_just_happened = False
        return was_set

    def peek_swap_just_happened(self) -> bool:
        """Return whether a swap is pending to be consumed (non-destructive)."""
        return self._swap_just_happened

    def swap_observers(self) -> tuple[str, str]:
        """Swap the two teams' ``current_observer_id`` values.

        Returns the pair of new observer IDs as ``(team_a_observer, team_b_observer)``.
        Raises ValueError if the world is not in two-team mode.
        """
        if TEAM_A_ID not in self._teams or TEAM_B_ID not in self._teams:
            raise ValueError("swap_observers requires two-team mode")
        team_a = self._teams[TEAM_A_ID]
        team_b = self._teams[TEAM_B_ID]
        team_a.current_observer_id, team_b.current_observer_id = (
            team_b.current_observer_id,
            team_a.current_observer_id,
        )
        return team_a.current_observer_id, team_b.current_observer_id

    def promote_intern_to_observer(self, intern_id: str) -> str:
        """Replace the solo team's current observer with ``intern_id``.

        Returns the ID of the displaced observer so the scenario can remove
        them from channels and stop injecting them. Raises ValueError if
        the world is not in single-team mode.
        """
        if TEAM_SOLO_ID not in self._teams:
            raise ValueError("promote_intern_to_observer requires single-team mode")
        team = self._teams[TEAM_SOLO_ID]
        displaced = team.current_observer_id
        team.current_observer_id = intern_id
        self._intern_takeover_just_happened = True
        return displaced

    def mark_intern_takeover(self) -> None:
        """Flag that the intern just took over; consumed by the next injection pass."""
        self._intern_takeover_just_happened = True

    def consume_intern_takeover(self) -> bool:
        """Return whether an intern takeover just happened and clear the flag."""
        was_set = self._intern_takeover_just_happened
        self._intern_takeover_just_happened = False
        return was_set

    def peek_intern_takeover(self) -> bool:
        """Return whether an intern takeover is pending to be consumed."""
        return self._intern_takeover_just_happened

    def get_team_for_agent(self, agent_id: str) -> TeamId:
        """Look up which team an agent currently belongs to.

        Observers are resolved by their current assignment; stabilization engineers by
        their fixed assignment. Raises ValueError for unknown agents.
        """
        for team_id, state in self._teams.items():
            if state.current_observer_id == agent_id:
                return team_id
            if state.stabilization_engineer_id == agent_id:
                return team_id
        raise ValueError(f"Unknown agent: {agent_id}")

    def get_outcomes_for_team(self, team_id: TeamId) -> list[VeyruOutcome]:
        """Return the list of outcomes recorded for the given team."""
        return self._teams[team_id].outcomes

    def compute_outcome_if_needed(self, round_number: int, team_id: TeamId) -> VeyruOutcome | None:
        """Compute and store the outcome for the given team/round if not already done.

        Returns the outcome, or None if no outcome can be computed (round 0).
        Used by postmortem injections to access results before the next round
        resets state.
        """
        if round_number < 1:
            return None

        team = self._teams[team_id]
        for existing in team.outcomes:
            if existing.case_number == round_number:
                return existing

        case_index = (round_number - 1) % len(self._veyru_cases)
        case = self._veyru_cases[case_index]
        time_elapsed = team.current_round_characters

        all_stage_outcomes = list(team.stage_outcomes)
        for i in range(len(all_stage_outcomes), len(case.stages)):
            all_stage_outcomes.append(
                StageOutcome(
                    motif_name=case.stages[i].motif_name,
                    stabilized=False,
                )
            )

        outcome = VeyruOutcome(
            team_id=team_id,
            case_number=round_number,
            failure_name=case.failure_name,
            stabilized=team.veyru_stabilized,
            characters_used=team.current_round_characters,
            time_elapsed_seconds=time_elapsed,
            time_budget_seconds=case.time_budget_seconds,
            stages_completed=len(team.stage_outcomes),
            total_stages=len(case.stages),
            stage_outcomes=tuple(all_stage_outcomes),
        )
        team.outcomes.append(outcome)
        return outcome

    def finalize_round_sync(self, round_number: int) -> None:
        """Compute previous round outcomes for all teams and reset per-round state.

        Called synchronously by the scenario's ``on_round_advanced`` before
        injections are delivered, so outcomes are available for templates.
        Each team survives only if its current field observer called
        ``stabilize_veyru`` during the round.
        """
        if round_number >= 2:
            for team_id in self._teams:
                self.compute_outcome_if_needed(
                    round_number=round_number - 1,
                    team_id=team_id,
                )

        for team in self._teams.values():
            team.reset_for_new_round()

        case_index = (round_number - 1) % len(self._veyru_cases)
        self._current_case = self._veyru_cases[case_index]

    def get_current_stage(self, team_id: TeamId) -> VeyruStage | None:
        """Return the active stage for a team, or None if no case is loaded."""
        if self._current_case is None:
            return None
        team = self._teams[team_id]
        if team.current_stage_index >= len(self._current_case.stages):
            return None
        return self._current_case.stages[team.current_stage_index]

    def is_veyru_alive(self, team_id: TeamId) -> bool:
        """Whether the team's current Veyru is still stable enough to be saved."""
        return self._teams[team_id].veyru_alive

    def is_veyru_stabilized(self, team_id: TeamId) -> bool:
        """Whether the team's current Veyru has been stabilized."""
        return self._teams[team_id].veyru_stabilized

    async def stabilize_veyru(self, team_id: TeamId) -> bool:
        """Advance to the next stage or fully stabilize the team's current Veyru.

        Records the current stage as stabilized. If more stages remain,
        advances the stage index and broadcasts a generic notification to
        the team's comm link (symptoms go to the observer via the tool
        result, not here). If all stages are done, marks the Veyru fully
        stabilized.

        Returns True if more stages remain, False if fully stabilized.
        """
        if self._current_case is None:
            return False

        team = self._teams[team_id]
        stage = self._current_case.stages[team.current_stage_index]
        team.stage_outcomes.append(StageOutcome(motif_name=stage.motif_name, stabilized=True))

        next_index = team.current_stage_index + 1
        if next_index >= len(self._current_case.stages):
            team.veyru_stabilized = True
            await self._context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=f"{VEYRU_STABILIZED_MARKER}. All issues resolved.",
            )
            return False

        team.current_stage_index = next_index
        await self._context.send_update_to_channel(
            channel_id=team.link_channel_id,
            text="Issue stabilized, but the Veyru remains unstable — new symptoms detected.",
        )
        return True

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate characters and update the affected team's state synchronously.

        Called from ``send_message`` before the event is enqueued, so
        ``stabilize_veyru`` sees correct state immediately. Messages on
        postmortem or non-link channels do not count toward the budget.
        """
        _ = agent_id, token_count
        team_id = self._channels_by_team.get(channel_id)
        if team_id is None:
            return

        team = self._teams[team_id]
        team.current_round_characters += len(text)

        if self._current_case is None:
            return
        if not team.veyru_alive:
            return
        if team.veyru_stabilized:
            return

        time_elapsed = team.current_round_characters
        budget = self._current_case.time_budget_seconds
        if time_elapsed > budget:
            team.veyru_alive = False

    async def run(self, context: WorldContext) -> None:
        """Process events and send async notifications for threshold crossings."""
        self._context = context
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    pass
                elif isinstance(event, MessageEvent):
                    team_id = self._channels_by_team.get(event.channel_id)
                    if team_id is None:
                        continue
                    await self._send_threshold_notifications(
                        context=context,
                        team_id=team_id,
                    )
        except asyncio.CancelledError:
            return

    async def _send_threshold_notifications(self, context: WorldContext, team_id: TeamId) -> None:
        """Send Veyru status notifications for a specific team when thresholds are crossed.

        Only two notification levels: CRITICAL at 75% budget used, and
        COLLAPSED at 100%. Notifications are delivered only to agents on
        the team's comm link so other teams do not see them.
        """
        if self._current_case is None:
            return

        team = self._teams[team_id]
        time_elapsed = team.current_round_characters
        budget = self._current_case.time_budget_seconds

        if not team.veyru_alive and THRESHOLD_COLLAPSED not in team.notified_thresholds:
            team.notified_thresholds.update([THRESHOLD_COLLAPSED, THRESHOLD_CRITICAL])
            await context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=(
                    f"{VEYRU_COLLAPSED_MARKER}. "
                    f"Communication time: {time_elapsed:.0f}s "
                    f"({team.current_round_characters} chars) "
                    f"exceeded budget of {budget}s."
                ),
            )
        elif team.veyru_stabilized:
            return
        elif time_elapsed > budget * 0.75 and THRESHOLD_CRITICAL not in team.notified_thresholds:
            team.notified_thresholds.add(THRESHOLD_CRITICAL)
            remaining = budget - time_elapsed
            await context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=(f"CRITICAL: Veyru destabilizing rapidly. {remaining:.0f} seconds remaining."),
            )
