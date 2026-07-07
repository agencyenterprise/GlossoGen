"""World simulation for the container_yard_stacking scenario.

Tracks per-team yard-row state, the single ``move_container`` action, and
the running character count on each team's link channel. The world is
mutated synchronously by the one scenario tool: the crane operator submits
a source slot and a destination slot, ``record_move`` judges them against
the round's ``YardCase`` ground truth and the live row, and mutates the row
on accept. Every mutating method takes a ``team_id`` so two-team mode can
fork per-team state without changing call sites.

A round relocates one or more target containers per team. Each relocation
is one "step": the team's crane operator moves the announced target to its
relative goal. Round success requires every step to be placed correctly and
the round budget not to have been exceeded.

Heavy logic lives in dedicated sibling modules: :mod:`judging` (move
scoring), :mod:`outcome_reconstruction` (rebuilding outcomes from a JSONL
event log on resume), and :mod:`world_state` (the ``TeamState`` /
``YardOutcome`` types).
"""

import asyncio
import logging
from typing import Any

from glossogen.runtime.scenario_world import RoundAdvancedEvent, ScenarioWorld, WorldContext
from glossogen.scenarios.container_yard_stacking.case_rendering import render_container
from glossogen.scenarios.container_yard_stacking.ids import (
    BUDGET_EXCEEDED_MARKER,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    ROUND_FAILED_MARKER,
    ROUND_SUCCESS_MARKER,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
)
from glossogen.scenarios.container_yard_stacking.judging import (
    MoveJudgement,
    last_failure_reason,
    record_move,
)
from glossogen.scenarios.container_yard_stacking.outcome_reconstruction import (
    restore_outcomes_from_events,
)
from glossogen.scenarios.container_yard_stacking.team_routing import team_id_for_channel
from glossogen.scenarios.container_yard_stacking.world_state import (
    StepOutcome,
    TeamState,
    YardOutcome,
)
from glossogen.scenarios.container_yard_stacking.yard_cases import YardCase

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"


__all__ = [
    "ContainerYardWorld",
    "StepOutcome",
    "TeamState",
    "YardOutcome",
]


class ContainerYardWorld(ScenarioWorld):
    """Per-team yard world that judges ``move_container`` calls deterministically.

    Single-team mode holds one ``TeamState`` keyed by ``TEAM_SOLO_ID``.
    Two-team mode holds two, keyed by ``TEAM_A_ID`` / ``TEAM_B_ID``. Every
    mutation method takes a ``team_id`` to select which team to update.
    """

    _context: WorldContext

    def __init__(
        self,
        cases: list[YardCase],
        postmortem_globally_disabled: bool,
        two_teams: bool,
    ) -> None:
        self._cases = cases
        self._two_teams = two_teams
        self._current_case: YardCase | None = None
        self._in_postmortem: bool = False
        self._postmortem_globally_disabled: bool = postmortem_globally_disabled
        self._teams: dict[str, TeamState] = self._build_teams(two_teams=two_teams)

    @staticmethod
    def _build_teams(two_teams: bool) -> dict[str, TeamState]:
        """Initialize the team-state map for single or two-team mode."""
        if two_teams:
            return {
                TEAM_A_ID: TeamState(team_id=TEAM_A_ID, link_channel_id=LINK_A_CHANNEL_ID),
                TEAM_B_ID: TeamState(team_id=TEAM_B_ID, link_channel_id=LINK_B_CHANNEL_ID),
            }
        return {
            TEAM_SOLO_ID: TeamState(team_id=TEAM_SOLO_ID, link_channel_id=LINK_CHANNEL_ID),
        }

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def two_teams(self) -> bool:
        """Whether the world is running two parallel teams."""
        return self._two_teams

    @property
    def team_ids(self) -> list[str]:
        """Stable list of the team identifiers this world tracks."""
        return list(self._teams.keys())

    @property
    def current_case(self) -> YardCase | None:
        """The yard case for the current round (shared across teams)."""
        return self._current_case

    def all_placed(self, team_id: str) -> bool:
        """Whether ``team_id`` has relocated every container in this round's batch."""
        case = self._current_case
        team = self._teams[team_id]
        if case is None:
            return False
        return team.placed_count >= len(case.steps)

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is in a postmortem discussion phase."""
        return self._in_postmortem

    @property
    def is_postmortem_disabled(self) -> bool:
        """Whether postmortem has been globally disabled."""
        return self._postmortem_globally_disabled

    def current_round_characters(self, team_id: str) -> int:
        """Running character count on ``team_id``'s link channel."""
        return self._teams[team_id].current_round_characters

    def round_budget_exceeded(self, team_id: str) -> bool:
        """Whether ``team_id`` has exceeded its communication budget this round."""
        return self._teams[team_id].round_budget_exceeded

    def round_failed_terminally(self, team_id: str) -> bool:
        """Whether ``team_id``'s current round has been marked unrecoverable."""
        return self._teams[team_id].round_failed_terminally

    def outcomes(self, team_id: str) -> list[YardOutcome]:
        """Historical per-round outcomes for one team."""
        return self._teams[team_id].outcomes

    def enter_postmortem(self) -> None:
        """Mark the start of a postmortem discussion phase."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Mark the end of a postmortem discussion phase."""
        self._in_postmortem = False

    def disable_postmortem_globally(self) -> None:
        """Close the postmortem channel for the rest of the simulation."""
        self._postmortem_globally_disabled = True

    def get_globally_disabled_channels(self) -> frozenset[str]:
        """Postmortem channels when disabled (single-team and two-team variants)."""
        if not self._postmortem_globally_disabled:
            return frozenset()
        return frozenset({POSTMORTEM_CHANNEL_ID, POSTMORTEM_A_CHANNEL_ID, POSTMORTEM_B_CHANNEL_ID})

    def previous_outcome(self, team_id: str) -> YardOutcome | None:
        """Return ``team_id``'s most recent outcome, or None when no rounds finished."""
        outcomes = self._teams[team_id].outcomes
        if len(outcomes) == 0:
            return None
        return outcomes[-1]

    def restore_outcomes_from_events(self, events: list[Any]) -> None:
        """Seed each team's ``outcomes`` from a JSONL event list on resume."""
        restore_outcomes_from_events(
            teams=self._teams,
            cases=self._cases,
            two_teams=self._two_teams,
            events=events,
        )

    def last_failure_reason(self, team_id: str) -> str:
        """Return ``team_id``'s most recently recorded failure reason for this round."""
        return last_failure_reason(team=self._teams[team_id])

    async def record_move(
        self,
        team_id: str,
        submitted_from_slot: int,
        submitted_to_slot: int,
    ) -> MoveJudgement:
        """Judge and apply one ``move_container`` call for ``team_id``."""
        assert self._current_case is not None, "record_move requires an active case"
        return await record_move(
            team=self._teams[team_id],
            case=self._current_case,
            context=self._context,
            submitted_from_slot=submitted_from_slot,
            submitted_to_slot=submitted_to_slot,
        )

    def mark_round_outcome(self, round_number: int) -> None:
        """Append outcomes for ``round_number`` to each team's outcome list."""
        for team in self._teams.values():
            if team.round_outcome_marked:
                continue
            self._mark_outcome(team=team, case_number=round_number)

    def finalize_round_sync(self, round_number: int) -> None:
        """Reset per-round state for every team and load the next case."""
        assert (
            1 <= round_number <= len(self._cases)
        ), f"round_number {round_number} out of range [1, {len(self._cases)}]"
        for team in self._teams.values():
            if round_number >= 2 and not team.round_outcome_marked:
                self._mark_outcome(team=team, case_number=round_number - 1)
        next_case = self._cases[round_number - 1]
        self._current_case = next_case
        for team in self._teams.values():
            team.current_round_characters = 0
            team.round_budget_exceeded = False
            team.notified_thresholds = set()
            team.round_failed_terminally = False
            team.failure_reason = ""
            team.round_outcome_marked = False
            team.placed_count = 0
            team.step_outcomes = []
            team.current_row = dict(next_case.initial_row)

    def round_succeeded(self, team_id: str) -> bool:
        """Return True when ``team_id`` placed every container within budget."""
        return self._round_succeeded(team_id=team_id)

    def _round_succeeded(self, team_id: str) -> bool:
        """Return True when ``team_id`` placed every container within budget."""
        case = self._current_case
        team = self._teams[team_id]
        if case is None:
            return False
        return (
            team.placed_count == len(case.steps)
            and not team.round_budget_exceeded
            and not team.round_failed_terminally
        )

    def _mark_outcome(self, team: TeamState, case_number: int) -> None:
        """Append a YardOutcome for ``team``'s just-finished round."""
        case = self._current_case
        if case is None:
            return
        all_step_outcomes: list[StepOutcome] = list(team.step_outcomes)
        placed_step_indices = {outcome.step_index for outcome in team.step_outcomes}
        for step in case.steps:
            if step.step_index in placed_step_indices:
                continue
            all_step_outcomes.append(
                StepOutcome(
                    step_index=step.step_index,
                    container_summary=render_container(container=step.container),
                    intake_slot=step.intake_slot,
                    target_slot=step.target_slot,
                    succeeded=False,
                )
            )
        all_step_outcomes.sort(key=lambda outcome: outcome.step_index)
        steps_succeeded = sum(1 for step in all_step_outcomes if step.succeeded)
        round_succeeded = self._round_succeeded(team_id=team.team_id)
        failure_step_index: int | None = None
        if not round_succeeded:
            for step in all_step_outcomes:
                if not step.succeeded:
                    failure_step_index = step.step_index
                    break
        team.outcomes.append(
            YardOutcome(
                case_number=case_number,
                team_id=team.team_id,
                step_count=len(case.steps),
                steps_succeeded=steps_succeeded,
                step_outcomes=tuple(all_step_outcomes),
                budget_exceeded=team.round_budget_exceeded,
                characters_used=team.current_round_characters,
                round_time_budget_seconds=case.round_time_budget_seconds,
                round_succeeded=round_succeeded,
                failure_reason=team.failure_reason,
                failure_step_index=failure_step_index,
            )
        )
        team.round_outcome_marked = True

    def swap_crane_operators(self) -> None:
        """No-op marker; the swap is implemented at the scenario level.

        The world tracks teams by ``team_id``, not by agent_id. Swapping
        agents is a scenario-side concern, so this hook is a no-op.
        """
        return None

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate characters and update budget state for the right team."""
        _ = agent_id, token_count
        team_id = team_id_for_channel(channel_id=channel_id)
        if team_id is None:
            return
        team = self._teams.get(team_id)
        if team is None:
            return
        team.current_round_characters += len(text)
        if self._current_case is None:
            return
        if team.current_round_characters >= self._current_case.round_time_budget_seconds:
            team.round_budget_exceeded = True
            team.round_failed_terminally = True
            if team.failure_reason == "":
                team.failure_reason = "Communication budget exhausted."

    async def run(self, context: WorldContext) -> None:
        """Process events and send async notifications for threshold crossings."""
        self._context = context
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    continue
                team_id = team_id_for_channel(channel_id=event.channel_id)
                if team_id is None:
                    continue
                await self._send_threshold_notifications(context=context, team_id=team_id)
        except asyncio.CancelledError:
            return

    async def _send_threshold_notifications(self, context: WorldContext, team_id: str) -> None:
        """Send status notifications for ``team_id`` when budget thresholds are crossed."""
        if self._current_case is None:
            return
        team = self._teams[team_id]
        time_elapsed = team.current_round_characters
        budget = self._current_case.round_time_budget_seconds
        if team.round_budget_exceeded and THRESHOLD_BUDGET_EXCEEDED not in team.notified_thresholds:
            team.notified_thresholds.update([THRESHOLD_BUDGET_EXCEEDED, THRESHOLD_CRITICAL])
            await context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. Communication time: "
                    f"{time_elapsed} chars exceeded budget of {budget}s."
                ),
            )
            return
        if time_elapsed >= budget * 0.75 and THRESHOLD_CRITICAL not in team.notified_thresholds:
            team.notified_thresholds.add(THRESHOLD_CRITICAL)
            remaining = budget - time_elapsed
            await context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=f"CRITICAL: Yard window narrowing. {remaining} seconds of budget remaining.",
            )

    async def emit_round_terminal_notification(self) -> None:
        """Emit each team's success / failure marker for the metric to pick up."""
        case = self._current_case
        if case is None:
            return
        for team in self._teams.values():
            if self._round_succeeded(team_id=team.team_id):
                text = (
                    f"{ROUND_SUCCESS_MARKER}. Placed all {len(case.steps)} container(s) "
                    "within budget."
                )
            else:
                if team.failure_reason != "":
                    reason = team.failure_reason
                else:
                    reason = "Round did not complete every placement."
                text = f"{ROUND_FAILED_MARKER}. {reason}"
            await self._context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=text,
            )
