"""World simulation for the container_yard_stacking scenario.

Tracks per-team yard state, truck commits, crane moves, and the running
character count on each team's link channel. The world is mutated
synchronously by the two scenario tools: structured ``move_truck`` args
feed ``record_truck_commit`` and structured ``crane_move`` args feed
``record_crane_move``. Every mutating method takes a ``team_id`` so
two-team mode can fork the per-team state without changing call sites.

A round delivers one or more incoming containers per team. Each
delivery is one "step": the team's yard operator commits trucks for
the step, the team's crane operator executes the step's planned moves,
and once the incoming container reaches its target the world advances
to the next step on that team. Round success requires every step to
complete with its expected trucks and moves and the round budget not
to have been exceeded.

Heavy logic lives in dedicated sibling modules:
:mod:`judging` (truck + crane scoring), :mod:`outcome_reconstruction`
(rebuilding outcomes from a JSONL event log on resume), and
:mod:`world_state` (the ``TeamState`` / ``YardOutcome`` types).
"""

import asyncio
import logging
from typing import Any

from schmidt.runtime.scenario_world import (
    MessageEvent,
    RoundAdvancedEvent,
    ScenarioWorld,
    WorldContext,
)
from schmidt.scenarios.container_yard_stacking.events import ContainerYardCraneMoveStep
from schmidt.scenarios.container_yard_stacking.ids import (
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
    YARD_OPERATOR_A_ID,
    YARD_OPERATOR_B_ID,
    YARD_OPERATOR_ID,
)
from schmidt.scenarios.container_yard_stacking.judging import (
    destination_is_free,
    find_assignment,
    last_failure_reason,
    pads_already_committed,
    record_crane_move,
    record_truck_commit,
    source_holds_container,
)
from schmidt.scenarios.container_yard_stacking.outcome_reconstruction import (
    restore_outcomes_from_events,
)
from schmidt.scenarios.container_yard_stacking.team_routing import team_id_for_channel
from schmidt.scenarios.container_yard_stacking.world_state import (
    StepOutcome,
    TeamState,
    TruckCommitResult,
    YardOutcome,
    stack_position_text,
)
from schmidt.scenarios.container_yard_stacking.yard_cases import CaseStep, TruckAssignment, YardCase

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"


__all__ = [
    "ContainerYardWorld",
    "StepOutcome",
    "TeamState",
    "TruckCommitResult",
    "YardOutcome",
]


class ContainerYardWorld(ScenarioWorld):
    """Per-team yard world that judges truck commits and crane moves deterministically.

    Single-team mode holds one ``TeamState`` keyed by ``TEAM_SOLO_ID``.
    Two-team mode holds two, keyed by ``TEAM_A_ID`` / ``TEAM_B_ID``.
    Every mutation method takes a ``team_id`` to select which team's
    state to update.
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
                TEAM_A_ID: TeamState(
                    team_id=TEAM_A_ID,
                    link_channel_id=LINK_A_CHANNEL_ID,
                    yard_operator_id=YARD_OPERATOR_A_ID,
                ),
                TEAM_B_ID: TeamState(
                    team_id=TEAM_B_ID,
                    link_channel_id=LINK_B_CHANNEL_ID,
                    yard_operator_id=YARD_OPERATOR_B_ID,
                ),
            }
        return {
            TEAM_SOLO_ID: TeamState(
                team_id=TEAM_SOLO_ID,
                link_channel_id=LINK_CHANNEL_ID,
                yard_operator_id=YARD_OPERATOR_ID,
            ),
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

    def current_step(self, team_id: str) -> CaseStep | None:
        """The step ``team_id`` is currently expecting trucks / moves for, if any."""
        case = self._current_case
        team = self._teams[team_id]
        if case is None:
            return None
        if team.current_step_index >= len(case.steps):
            return None
        return case.steps[team.current_step_index]

    def _next_step(self, team_id: str) -> CaseStep | None:
        """The step that becomes active for ``team_id`` after the current step completes."""
        case = self._current_case
        team = self._teams[team_id]
        if case is None:
            return None
        next_index = team.current_step_index + 1
        if next_index >= len(case.steps):
            return None
        return case.steps[next_index]

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

    def step_accepted_move_count(self, team_id: str) -> int:
        """Crane moves accepted for ``team_id``'s current step so far."""
        return self._teams[team_id].step_accepted_move_count

    def round_failed_terminally(self, team_id: str) -> bool:
        """Whether ``team_id``'s current round has been marked unrecoverable."""
        return self._teams[team_id].round_failed_terminally

    def outcomes(self, team_id: str) -> list[YardOutcome]:
        """Historical per-round outcomes for one team."""
        return self._teams[team_id].outcomes

    def truck_arrived(self, team_id: str, truck_role: str) -> bool:
        """Whether ``team_id``'s named truck role has arrived at its correct spot."""
        state = self._teams[team_id].truck_states.get(truck_role)
        if state is None:
            return False
        return state.arrived

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
        """Seed each team's ``outcomes`` from a JSONL event list on resume.

        Delegates to :func:`outcome_reconstruction.restore_outcomes_from_events`
        which walks the truck/crane verdicts and link-channel messages to
        recover one ``YardOutcome`` per completed round per team.
        """
        restore_outcomes_from_events(
            teams=self._teams,
            cases=self._cases,
            two_teams=self._two_teams,
            events=events,
        )

    def find_assignment(self, team_id: str, truck_role: str) -> TruckAssignment | None:
        """Return ``team_id``'s current step's ground-truth assignment for ``truck_role``."""
        return find_assignment(
            current_step=self.current_step(team_id=team_id),
            truck_role=truck_role,
        )

    async def record_truck_commit(
        self,
        team_id: str,
        parsed_truck_role: str,
        parsed_pad: str,
        role_matches_active_assignment: bool,
        targets_correct_station: bool,
        targets_correct_pad: bool,
        carries_correct_container: bool,
    ) -> TruckCommitResult:
        """Update ``team_id``'s state with the verdict for one ``move_truck`` call."""
        if self._current_case is None:
            return TruckCommitResult(
                truck_role=parsed_truck_role,
                accepted=False,
                duplicate=False,
            )
        return await record_truck_commit(
            team=self._teams[team_id],
            current_step=self.current_step(team_id=team_id),
            context=self._context,
            parsed_truck_role=parsed_truck_role,
            parsed_pad=parsed_pad,
            role_matches_active_assignment=role_matches_active_assignment,
            targets_correct_station=targets_correct_station,
            targets_correct_pad=targets_correct_pad,
            carries_correct_container=carries_correct_container,
        )

    def pads_already_committed(self, team_id: str) -> list[str]:
        """Return non-empty pads currently bound to a truck for ``team_id``'s current step."""
        return pads_already_committed(team=self._teams[team_id])

    def source_holds_container(
        self, team_id: str, kind: str, stack: int | None, container_id: str
    ) -> bool:
        """Return True when ``team_id``'s named source currently carries ``container_id``."""
        return source_holds_container(
            team=self._teams[team_id], kind=kind, stack=stack, container_id=container_id
        )

    def destination_is_free(
        self, team_id: str, kind: str, stack: int | None, tier: int | None
    ) -> bool:
        """Return True when ``team_id``'s named destination is free for a crane drop."""
        return destination_is_free(team=self._teams[team_id], kind=kind, stack=stack, tier=tier)

    def last_failure_reason(self, team_id: str) -> str:
        """Return ``team_id``'s most recently recorded failure reason for this round."""
        return last_failure_reason(team=self._teams[team_id])

    async def record_crane_move(
        self,
        team_id: str,
        parsed_move: ContainerYardCraneMoveStep,
        parsed_source_kind: str,
        parsed_source_stack: int | None,
        parsed_destination_kind: str,
        parsed_destination_stack: int | None,
        matches_expected_next_move: bool,
        source_currently_holds_container: bool,
        destination_currently_empty: bool,
    ) -> bool:
        """Apply or reject a crane move for ``team_id`` and emit a notification."""
        return await record_crane_move(
            team=self._teams[team_id],
            current_step=self.current_step(team_id=team_id),
            next_step=self._next_step(team_id=team_id),
            context=self._context,
            parsed_move=parsed_move,
            parsed_source_kind=parsed_source_kind,
            parsed_source_stack=parsed_source_stack,
            parsed_destination_kind=parsed_destination_kind,
            parsed_destination_stack=parsed_destination_stack,
            matches_expected_next_move=matches_expected_next_move,
            source_currently_holds_container=source_currently_holds_container,
            destination_currently_empty=destination_currently_empty,
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
            team.truck_states = {}
            team.round_failed_terminally = False
            team.failure_reason = ""
            team.round_outcome_marked = False
            team.current_step_index = 0
            team.step_accepted_move_count = 0
            team.step_correctly_committed_truck_count = 0
            team.step_outcomes = []
            team.current_stacks = {
                stack_index: list(containers)
                for stack_index, containers in next_case.initial_stacks.items()
            }

    def round_succeeded(self, team_id: str) -> bool:
        """Return True when ``team_id`` completed every step within budget."""
        return self._round_succeeded(team_id=team_id)

    def _round_succeeded(self, team_id: str) -> bool:
        """Return True when ``team_id`` completed every step within budget."""
        case = self._current_case
        team = self._teams[team_id]
        if case is None:
            return False
        return (
            team.current_step_index == len(case.steps)
            and not team.round_budget_exceeded
            and not team.round_failed_terminally
        )

    def _mark_outcome(self, team: TeamState, case_number: int) -> None:
        """Append a YardOutcome for ``team``'s just-finished round."""
        case = self._current_case
        if case is None:
            return
        all_step_outcomes: list[StepOutcome] = list(team.step_outcomes)
        if team.current_step_index < len(case.steps):
            in_progress_step = case.steps[team.current_step_index]
            all_step_outcomes.append(
                StepOutcome(
                    step_index=in_progress_step.step_index,
                    incoming_container_id=in_progress_step.incoming_container_id,
                    target_position_text=stack_position_text(
                        stack=in_progress_step.target_position.stack,
                        tier=in_progress_step.target_position.tier,
                    ),
                    succeeded=False,
                    expected_move_count=len(in_progress_step.expected_move_sequence),
                    accepted_move_count=team.step_accepted_move_count,
                    expected_truck_count=len(in_progress_step.truck_assignments),
                    correctly_committed_truck_count=team.step_correctly_committed_truck_count,
                )
            )
        for remaining in case.steps[team.current_step_index + 1 :]:
            all_step_outcomes.append(
                StepOutcome(
                    step_index=remaining.step_index,
                    incoming_container_id=remaining.incoming_container_id,
                    target_position_text=stack_position_text(
                        stack=remaining.target_position.stack,
                        tier=remaining.target_position.tier,
                    ),
                    succeeded=False,
                    expected_move_count=len(remaining.expected_move_sequence),
                    accepted_move_count=0,
                    expected_truck_count=len(remaining.truck_assignments),
                    correctly_committed_truck_count=0,
                )
            )
        steps_succeeded = sum(1 for step in all_step_outcomes if step.succeeded)
        round_succeeded = self._round_succeeded(team_id=team.team_id)
        total_expected_moves = sum(s.expected_move_count for s in all_step_outcomes)
        total_accepted_moves = sum(s.accepted_move_count for s in all_step_outcomes)
        total_expected_trucks = sum(s.expected_truck_count for s in all_step_outcomes)
        total_correctly_committed_trucks = sum(
            s.correctly_committed_truck_count for s in all_step_outcomes
        )
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
                total_expected_move_count=total_expected_moves,
                total_accepted_move_count=total_accepted_moves,
                total_expected_truck_count=total_expected_trucks,
                total_correctly_committed_truck_count=total_correctly_committed_trucks,
                budget_exceeded=team.round_budget_exceeded,
                characters_used=team.current_round_characters,
                time_budget_seconds=case.time_budget_seconds,
                round_succeeded=round_succeeded,
                failure_reason=team.failure_reason,
                failure_step_index=failure_step_index,
            )
        )
        team.round_outcome_marked = True

    def swap_crane_operators(self) -> None:
        """No-op marker; the swap is implemented at the scenario level.

        The world tracks teams by ``team_id``, not by agent_id. Swapping
        agents is a scenario-side concern (handled by reassigning
        ``AgentConfig``), so this hook is intentionally a no-op.
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
        if team.current_round_characters >= self._current_case.time_budget_seconds:
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
                if isinstance(event, MessageEvent):
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
        budget = self._current_case.time_budget_seconds
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
                    reason = "Round did not complete every delivery."
                text = f"{ROUND_FAILED_MARKER}. {reason}"
            await self._context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=text,
            )
