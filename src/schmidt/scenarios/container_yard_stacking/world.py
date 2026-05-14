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
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from schmidt.models.event import MessageSent, RoundEnded
from schmidt.runtime.scenario_world import (
    MessageEvent,
    RoundAdvancedEvent,
    ScenarioWorld,
    WorldContext,
)
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCraneMoveJudged,
    ContainerYardCraneMoveStep,
    ContainerYardTruckJudged,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    BUDGET_EXCEEDED_MARKER,
    CONTAINER_PLACED_MARKER,
    INBOUND_TRUCK_ROLE,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    OUTBOUND_TRUCK_ROLE,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    ROUND_FAILED_MARKER,
    ROUND_SUCCESS_MARKER,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TRUCK_ARRIVED_MARKER,
    TRUCK_WRONG_SPOT_MARKER,
    YARD_OPERATOR_A_ID,
    YARD_OPERATOR_B_ID,
    YARD_OPERATOR_ID,
)
from schmidt.scenarios.container_yard_stacking.yard_cases import CaseStep, TruckAssignment, YardCase

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"

NEXT_CONTAINER_MARKER = "NEXT INCOMING CONTAINER"


class TruckState(NamedTuple):
    """Live per-step position and contents of one truck."""

    truck_role: str
    arrived: bool
    station_name: str
    pad: str
    container_id: str


class TruckCommitResult(NamedTuple):
    """Outcome of a single ``record_truck_commit`` call."""

    truck_role: str
    accepted: bool
    duplicate: bool


class StepOutcome(NamedTuple):
    """One step's recorded outcome within a completed round."""

    step_index: int
    incoming_container_id: str
    target_position_text: str
    succeeded: bool
    expected_move_count: int
    accepted_move_count: int
    expected_truck_count: int
    correctly_committed_truck_count: int


class YardOutcome(NamedTuple):
    """Result of a single yard case after a round completes for one team."""

    case_number: int
    team_id: str
    step_count: int
    steps_succeeded: int
    step_outcomes: tuple[StepOutcome, ...]
    total_expected_move_count: int
    total_accepted_move_count: int
    total_expected_truck_count: int
    total_correctly_committed_truck_count: int
    budget_exceeded: bool
    characters_used: int
    time_budget_seconds: int
    round_succeeded: bool
    failure_reason: str
    failure_step_index: int | None


@dataclass
class _TeamState:
    """All per-team mutable state the world tracks for one team."""

    team_id: str
    link_channel_id: str
    yard_operator_id: str
    current_round_characters: int = 0
    round_budget_exceeded: bool = False
    notified_thresholds: set[str] = field(default_factory=set)
    outcomes: list[YardOutcome] = field(default_factory=list)
    current_stacks: dict[int, list[str]] = field(default_factory=dict)
    truck_states: dict[str, TruckState] = field(default_factory=dict)
    round_failed_terminally: bool = False
    failure_reason: str = ""
    round_outcome_marked: bool = False
    current_step_index: int = 0
    step_accepted_move_count: int = 0
    step_correctly_committed_truck_count: int = 0
    step_outcomes: list[StepOutcome] = field(default_factory=list)


class ContainerYardWorld(ScenarioWorld):
    """Per-team yard world that judges truck commits and crane moves deterministically.

    Single-team mode holds one ``_TeamState`` keyed by ``TEAM_SOLO_ID``.
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
        self._teams: dict[str, _TeamState] = self._build_teams(two_teams=two_teams)

    @staticmethod
    def _build_teams(two_teams: bool) -> dict[str, _TeamState]:
        """Initialize the team-state map for single or two-team mode."""
        if two_teams:
            return {
                TEAM_A_ID: _TeamState(
                    team_id=TEAM_A_ID,
                    link_channel_id=LINK_A_CHANNEL_ID,
                    yard_operator_id=YARD_OPERATOR_A_ID,
                ),
                TEAM_B_ID: _TeamState(
                    team_id=TEAM_B_ID,
                    link_channel_id=LINK_B_CHANNEL_ID,
                    yard_operator_id=YARD_OPERATOR_B_ID,
                ),
            }
        return {
            TEAM_SOLO_ID: _TeamState(
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

        Walks the per-round truck and crane verdict events, sums each
        team's link-channel message lengths to derive ``characters_used``
        and ``budget_exceeded``, and appends one ``YardOutcome`` per
        team per round whose ``RoundEnded`` event was logged. Without
        this, an injection rendered right after resume would render a
        blank "previous round" block.
        """
        trucks_by_round_step_team: dict[
            int, dict[str, dict[int, list[ContainerYardTruckJudged]]]
        ] = {}
        cranes_by_round_step_team: dict[
            int, dict[str, dict[int, list[ContainerYardCraneMoveJudged]]]
        ] = {}
        characters_by_round_team: dict[int, dict[str, int]] = {}
        completed_rounds: set[int] = set()
        for event in events:
            round_number = getattr(event, "round_number", None)
            if not isinstance(round_number, int) or round_number < 1:
                continue
            if isinstance(event, ContainerYardTruckJudged):
                truck_team_id = self._team_id_for_agent(agent_id=event.agent_id)
                truck_step_buckets = trucks_by_round_step_team.setdefault(
                    round_number, {}
                ).setdefault(truck_team_id, {})
                truck_step_buckets.setdefault(event.step_index, []).append(event)
            elif isinstance(event, ContainerYardCraneMoveJudged):
                crane_team_id = self._team_id_for_agent(agent_id=event.agent_id)
                crane_step_buckets = cranes_by_round_step_team.setdefault(
                    round_number, {}
                ).setdefault(crane_team_id, {})
                crane_step_buckets.setdefault(event.step_index, []).append(event)
            elif isinstance(event, MessageSent):
                message_team_id = self._team_id_for_channel(channel_id=event.message.channel_id)
                if message_team_id is None:
                    continue
                bucket = characters_by_round_team.setdefault(round_number, {})
                bucket[message_team_id] = bucket.get(message_team_id, 0) + len(event.message.text)
            elif isinstance(event, RoundEnded):
                completed_rounds.add(round_number)
        for round_number in sorted(completed_rounds):
            if round_number > len(self._cases):
                continue
            for team_id, team in self._teams.items():
                if any(o.case_number == round_number for o in team.outcomes):
                    continue
                team.outcomes.append(
                    self._reconstruct_outcome(
                        round_number=round_number,
                        team_id=team_id,
                        trucks_by_step=trucks_by_round_step_team.get(round_number, {}).get(
                            team_id, {}
                        ),
                        cranes_by_step=cranes_by_round_step_team.get(round_number, {}).get(
                            team_id, {}
                        ),
                        characters_used=characters_by_round_team.get(round_number, {}).get(
                            team_id, 0
                        ),
                    )
                )

    def _team_id_for_agent(self, agent_id: str) -> str:
        """Map an agent_id back to the team it belongs to."""
        if not self._two_teams:
            return TEAM_SOLO_ID
        if agent_id.endswith("_a"):
            return TEAM_A_ID
        if agent_id.endswith("_b"):
            return TEAM_B_ID
        return TEAM_SOLO_ID

    def _team_id_for_channel(self, channel_id: str) -> str | None:
        """Map a channel_id to its team, or None for unrelated channels."""
        if channel_id == LINK_CHANNEL_ID:
            return TEAM_SOLO_ID
        if channel_id == LINK_A_CHANNEL_ID:
            return TEAM_A_ID
        if channel_id == LINK_B_CHANNEL_ID:
            return TEAM_B_ID
        return None

    def _reconstruct_outcome(
        self,
        round_number: int,
        team_id: str,
        trucks_by_step: dict[int, list[ContainerYardTruckJudged]],
        cranes_by_step: dict[int, list[ContainerYardCraneMoveJudged]],
        characters_used: int,
    ) -> YardOutcome:
        """Build a ``YardOutcome`` for a completed round from grouped events."""
        case = self._cases[round_number - 1]
        budget_exceeded = characters_used >= case.time_budget_seconds
        step_outcomes: list[StepOutcome] = []
        failure_step_index: int | None = None
        first_failure_explanation = ""
        for step in case.steps:
            trucks_for_step = trucks_by_step.get(step.step_index, [])
            cranes_for_step = cranes_by_step.get(step.step_index, [])
            committed_count = sum(1 for t in trucks_for_step if t.overall_success)
            accepted_move_count = sum(1 for c in cranes_for_step if c.accepted)
            expected_truck_count = len(step.truck_assignments)
            expected_move_count = len(step.expected_move_sequence)
            succeeded = (
                committed_count == expected_truck_count
                and accepted_move_count == expected_move_count
            )
            step_outcomes.append(
                StepOutcome(
                    step_index=step.step_index,
                    incoming_container_id=step.incoming_container_id,
                    target_position_text=_stack_position_text(
                        stack=step.target_position.stack,
                        tier=step.target_position.tier,
                    ),
                    succeeded=succeeded,
                    expected_move_count=expected_move_count,
                    accepted_move_count=accepted_move_count,
                    expected_truck_count=expected_truck_count,
                    correctly_committed_truck_count=committed_count,
                )
            )
            if not succeeded and failure_step_index is None:
                failure_step_index = step.step_index
                first_failure_explanation = _first_failure_explanation(
                    trucks_for_step=trucks_for_step,
                    cranes_for_step=cranes_for_step,
                )
        steps_succeeded = sum(1 for s in step_outcomes if s.succeeded)
        round_succeeded = steps_succeeded == len(case.steps) and not budget_exceeded
        if round_succeeded:
            failure_reason = ""
        elif budget_exceeded:
            failure_reason = "Communication budget exhausted."
        elif first_failure_explanation != "":
            failure_reason = first_failure_explanation
        else:
            failure_reason = "Round did not complete every delivery."
        return YardOutcome(
            case_number=round_number,
            team_id=team_id,
            step_count=len(case.steps),
            steps_succeeded=steps_succeeded,
            step_outcomes=tuple(step_outcomes),
            total_expected_move_count=sum(s.expected_move_count for s in step_outcomes),
            total_accepted_move_count=sum(s.accepted_move_count for s in step_outcomes),
            total_expected_truck_count=sum(s.expected_truck_count for s in step_outcomes),
            total_correctly_committed_truck_count=sum(
                s.correctly_committed_truck_count for s in step_outcomes
            ),
            budget_exceeded=budget_exceeded,
            characters_used=characters_used,
            time_budget_seconds=case.time_budget_seconds,
            round_succeeded=round_succeeded,
            failure_reason=failure_reason,
            failure_step_index=failure_step_index,
        )

    def find_assignment(self, team_id: str, truck_role: str) -> TruckAssignment | None:
        """Return ``team_id``'s current step's ground-truth assignment for ``truck_role``."""
        step = self.current_step(team_id=team_id)
        if step is None:
            return None
        for assignment in step.truck_assignments:
            if assignment.truck_role == truck_role:
                return assignment
        return None

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
        team = self._teams[team_id]
        if self._current_case is None or self.current_step(team_id=team_id) is None:
            return TruckCommitResult(
                truck_role=parsed_truck_role,
                accepted=False,
                duplicate=False,
            )
        if parsed_truck_role in team.truck_states:
            return TruckCommitResult(
                truck_role=parsed_truck_role,
                accepted=False,
                duplicate=True,
            )
        assignment = self.find_assignment(team_id=team_id, truck_role=parsed_truck_role)
        pad_already_used = parsed_pad != "" and parsed_pad in self.pads_already_committed(
            team_id=team_id
        )
        role_known = assignment is not None
        all_correct = (
            role_matches_active_assignment
            and targets_correct_station
            and targets_correct_pad
            and carries_correct_container
            and role_known
            and not pad_already_used
        )
        if not all_correct:
            team.round_failed_terminally = True
            reason = _truck_failure_reason(
                parsed_truck_role=parsed_truck_role,
                role_matches_active_assignment=role_matches_active_assignment,
                targets_correct_station=targets_correct_station,
                targets_correct_pad=targets_correct_pad,
                carries_correct_container=carries_correct_container,
                role_known=role_known,
                pad_already_used=pad_already_used,
            )
            if team.failure_reason == "":
                team.failure_reason = reason
            team.truck_states[parsed_truck_role] = TruckState(
                truck_role=parsed_truck_role,
                arrived=False,
                station_name="",
                pad="",
                container_id="",
            )
            await self._context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=f"{parsed_truck_role.upper()} {TRUCK_WRONG_SPOT_MARKER}. {reason}",
            )
            return TruckCommitResult(
                truck_role=parsed_truck_role,
                accepted=False,
                duplicate=False,
            )
        accepted_assignment = assignment
        assert accepted_assignment is not None
        team.truck_states[parsed_truck_role] = TruckState(
            truck_role=parsed_truck_role,
            arrived=True,
            station_name=accepted_assignment.station_name,
            pad=parsed_pad,
            container_id=accepted_assignment.container_id,
        )
        team.step_correctly_committed_truck_count += 1
        await self._context.send_update_to_channel(
            channel_id=team.link_channel_id,
            text=(
                f"{parsed_truck_role.upper()} {TRUCK_ARRIVED_MARKER}. The truck is "
                f"positioned at {accepted_assignment.station_name}, {parsed_pad} and is ready "
                "for the crane."
            ),
        )
        return TruckCommitResult(
            truck_role=parsed_truck_role,
            accepted=True,
            duplicate=False,
        )

    def pads_already_committed(self, team_id: str) -> list[str]:
        """Return non-empty pads currently bound to a truck for ``team_id``'s current step."""
        return [
            state.pad
            for state in self._teams[team_id].truck_states.values()
            if state.arrived and state.pad != ""
        ]

    def source_holds_container(
        self, team_id: str, kind: str, stack: int | None, container_id: str
    ) -> bool:
        """Return True when ``team_id``'s named source currently carries ``container_id``."""
        team = self._teams[team_id]
        if kind == "inbound_truck":
            state = team.truck_states.get(INBOUND_TRUCK_ROLE)
            return state is not None and state.arrived and state.container_id == container_id
        if kind == "outbound_truck":
            state = team.truck_states.get(OUTBOUND_TRUCK_ROLE)
            return state is not None and state.arrived and state.container_id == container_id
        if kind == "stack_tier":
            if stack is None or stack not in team.current_stacks:
                return False
            contents = team.current_stacks[stack]
            return len(contents) > 0 and contents[-1] == container_id
        return False

    def destination_is_free(
        self, team_id: str, kind: str, stack: int | None, tier: int | None
    ) -> bool:
        """Return True when ``team_id``'s named destination is free for a crane drop."""
        team = self._teams[team_id]
        if kind == "inbound_truck":
            return False
        if kind == "outbound_truck":
            state = team.truck_states.get(OUTBOUND_TRUCK_ROLE)
            return state is not None and state.arrived and state.container_id == ""
        if kind == "stack_tier":
            if stack is None or stack not in team.current_stacks or tier is None:
                return False
            return tier == len(team.current_stacks[stack]) + 1
        return False

    def last_failure_reason(self, team_id: str) -> str:
        """Return ``team_id``'s most recently recorded failure reason for this round."""
        team = self._teams[team_id]
        if team.failure_reason == "":
            return "Crane move rejected."
        return team.failure_reason

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
        team = self._teams[team_id]
        step = self.current_step(team_id=team_id)
        if step is None:
            return False
        round_already_failed = team.round_failed_terminally
        sequence_already_exhausted = team.step_accepted_move_count >= len(
            step.expected_move_sequence
        )
        structural_invariant_holds = self._structural_invariants_hold(
            team_id=team_id,
            container_id=parsed_move.container_id,
            source_kind=parsed_source_kind,
            source_stack=parsed_source_stack,
            destination_kind=parsed_destination_kind,
            destination_stack=parsed_destination_stack,
        )
        accepted = (
            matches_expected_next_move
            and source_currently_holds_container
            and destination_currently_empty
            and not round_already_failed
            and not sequence_already_exhausted
            and structural_invariant_holds
        )
        if not accepted:
            team.round_failed_terminally = True
            reason = _crane_failure_reason(
                matches_expected_next_move=matches_expected_next_move,
                source_currently_holds_container=source_currently_holds_container,
                destination_currently_empty=destination_currently_empty,
                round_already_failed=round_already_failed,
                sequence_already_exhausted=sequence_already_exhausted,
                structural_invariant_holds=structural_invariant_holds,
            )
            if team.failure_reason == "":
                team.failure_reason = reason
            return False
        self._apply_move_to_state(
            team_id=team_id,
            parsed_move=parsed_move,
            source_kind=parsed_source_kind,
            source_stack=parsed_source_stack,
            destination_kind=parsed_destination_kind,
            destination_stack=parsed_destination_stack,
        )
        team.step_accepted_move_count += 1
        if self._incoming_container_at_target_for_step(team_id=team_id, step=step):
            target_text = _stack_position_text(
                stack=step.target_position.stack,
                tier=step.target_position.tier,
            )
            await self._context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=(
                    f"{CONTAINER_PLACED_MARKER}. {step.incoming_container_id} "
                    f"is now at {target_text}."
                ),
            )
            await self._advance_step(team_id=team_id)
        return True

    async def _advance_step(self, team_id: str) -> None:
        """Close ``team_id``'s current step and reveal the next step's container ID."""
        case = self._current_case
        team = self._teams[team_id]
        step = self.current_step(team_id=team_id)
        assert case is not None and step is not None
        team.step_outcomes.append(
            StepOutcome(
                step_index=step.step_index,
                incoming_container_id=step.incoming_container_id,
                target_position_text=_stack_position_text(
                    stack=step.target_position.stack, tier=step.target_position.tier
                ),
                succeeded=True,
                expected_move_count=len(step.expected_move_sequence),
                accepted_move_count=team.step_accepted_move_count,
                expected_truck_count=len(step.truck_assignments),
                correctly_committed_truck_count=team.step_correctly_committed_truck_count,
            )
        )
        team.current_step_index += 1
        team.truck_states = {}
        team.step_accepted_move_count = 0
        team.step_correctly_committed_truck_count = 0
        next_step = self.current_step(team_id=team_id)
        if next_step is not None:
            await self._context.send_update_to_agent(
                agent_id=team.yard_operator_id,
                text=(
                    f"{NEXT_CONTAINER_MARKER}: {next_step.incoming_container_id}. "
                    "Share this with the planner the same way you shared the first."
                ),
            )

    def _structural_invariants_hold(
        self,
        team_id: str,
        container_id: str,
        source_kind: str,
        source_stack: int | None,
        destination_kind: str,
        destination_stack: int | None,
    ) -> bool:
        """Verify the parsed move's structural invariants against ``team_id``'s live state."""
        team = self._teams[team_id]
        if source_kind == "outbound_truck":
            return False
        if destination_kind == "inbound_truck":
            return False
        if source_kind == "inbound_truck":
            state = team.truck_states.get(INBOUND_TRUCK_ROLE)
            if state is None or not state.arrived or state.container_id != container_id:
                return False
        elif source_kind == "stack_tier":
            if source_stack is None or source_stack not in team.current_stacks:
                return False
            stack_contents = team.current_stacks[source_stack]
            if len(stack_contents) == 0 or stack_contents[-1] != container_id:
                return False
        else:
            return False
        if destination_kind == "outbound_truck":
            state = team.truck_states.get(OUTBOUND_TRUCK_ROLE)
            if state is None or not state.arrived or state.container_id != "":
                return False
        elif destination_kind == "stack_tier":
            if destination_stack is None or destination_stack not in team.current_stacks:
                return False
        else:
            return False
        return True

    def _incoming_container_at_target_for_step(self, team_id: str, step: CaseStep) -> bool:
        """Return True when ``step``'s incoming container has reached its target slot."""
        team = self._teams[team_id]
        stack_contents = team.current_stacks.get(step.target_position.stack)
        if stack_contents is None:
            return False
        if len(stack_contents) < step.target_position.tier:
            return False
        tier_index = step.target_position.tier - 1
        return stack_contents[tier_index] == step.incoming_container_id

    def _apply_move_to_state(
        self,
        team_id: str,
        parsed_move: ContainerYardCraneMoveStep,
        source_kind: str,
        source_stack: int | None,
        destination_kind: str,
        destination_stack: int | None,
    ) -> None:
        """Mutate ``team_id``'s stack and truck state to reflect an accepted move."""
        team = self._teams[team_id]
        container_id = parsed_move.container_id
        if source_kind == "inbound_truck":
            self._unload_truck(team=team, truck_role=INBOUND_TRUCK_ROLE)
        elif source_kind == "stack_tier":
            assert source_stack is not None
            team.current_stacks[source_stack].pop()
        if destination_kind == "outbound_truck":
            self._load_truck(team=team, truck_role=OUTBOUND_TRUCK_ROLE, container_id=container_id)
        elif destination_kind == "stack_tier":
            assert destination_stack is not None
            team.current_stacks[destination_stack].append(container_id)

    def _unload_truck(self, team: _TeamState, truck_role: str) -> None:
        """Mark ``truck_role`` as empty on ``team``."""
        state = team.truck_states.get(truck_role)
        if state is None:
            return
        team.truck_states[truck_role] = state._replace(container_id="")

    def _load_truck(self, team: _TeamState, truck_role: str, container_id: str) -> None:
        """Mark ``truck_role`` as carrying ``container_id`` on ``team``."""
        state = team.truck_states.get(truck_role)
        if state is None:
            return
        team.truck_states[truck_role] = state._replace(container_id=container_id)

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

    def round_succeeded(self, team_id: str) -> bool:
        """Public wrapper for :meth:`_round_succeeded` used by ``judge_round_result``."""
        return self._round_succeeded(team_id=team_id)

    def _mark_outcome(self, team: _TeamState, case_number: int) -> None:
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
                    target_position_text=_stack_position_text(
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
                    target_position_text=_stack_position_text(
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
        """Exchange the yard_operator_id between team A and B (used by the swap mechanic).

        After this fires, future tool calls from ``crane_operator_a`` /
        ``crane_operator_b`` route to the same world team they have
        always routed to, but the agent itself is the swapped
        instance. The world bookkeeping does not need to change — only
        the scenario-level agent identity does. Provided as a hook for
        future expansion; today the swap is implemented in the scenario.
        """
        # The world tracks teams by team_id, not by agent_id. Swapping
        # agents is a scenario-side concern (handled by reassigning
        # AgentConfig), so this hook is intentionally a no-op marker.
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
        team_id = self._team_id_for_channel(channel_id=channel_id)
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
                    team_id = self._team_id_for_channel(channel_id=event.channel_id)
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


def _stack_position_text(stack: int, tier: int) -> str:
    """Return the canonical "Stack S, Tier T" position string."""
    return f"Stack {stack}, Tier {tier}"


def _first_failure_explanation(
    trucks_for_step: list[ContainerYardTruckJudged],
    cranes_for_step: list[ContainerYardCraneMoveJudged],
) -> str:
    """Return the explanation string of the first failed truck or crane verdict for a step."""
    for truck in trucks_for_step:
        if not truck.overall_success:
            return truck.explanation
    for crane in cranes_for_step:
        if not crane.accepted:
            return crane.explanation
    return ""


def _truck_failure_reason(
    parsed_truck_role: str,
    role_matches_active_assignment: bool,
    targets_correct_station: bool,
    targets_correct_pad: bool,
    carries_correct_container: bool,
    role_known: bool,
    pad_already_used: bool,
) -> str:
    """Build a specific failure-reason string from the truck verdict's per-criterion booleans."""
    reasons: list[str] = []
    if not role_matches_active_assignment:
        reasons.append("role does not match any active assignment for this step")
    elif not role_known:
        reasons.append(f"no assignment matches the parsed role {parsed_truck_role!r}")
    if not targets_correct_station:
        reasons.append("destination text does not identify the correct crane station")
    if not targets_correct_pad:
        reasons.append("destination pad is not a free pad at the correct station")
    if not carries_correct_container:
        reasons.append("inbound text does not name the correct incoming container")
    if pad_already_used:
        reasons.append("destination pad is already used by another truck this step")
    if not reasons:
        return f"{parsed_truck_role} truck did not arrive at the correct spot."
    return (
        f"{parsed_truck_role} truck did not arrive at the correct spot: " + "; ".join(reasons) + "."
    )


def _crane_failure_reason(
    matches_expected_next_move: bool,
    source_currently_holds_container: bool,
    destination_currently_empty: bool,
    round_already_failed: bool,
    sequence_already_exhausted: bool,
    structural_invariant_holds: bool,
) -> str:
    """Build a specific failure-reason string from the crane verdict's per-criterion booleans."""
    reasons: list[str] = []
    if not matches_expected_next_move:
        reasons.append("move did not match the expected next step")
    if not source_currently_holds_container:
        reasons.append("source does not currently hold the named container")
    if not destination_currently_empty:
        reasons.append("destination is not currently empty")
    if round_already_failed:
        reasons.append("round was already terminally failed before this move")
    if sequence_already_exhausted:
        reasons.append("all expected moves for this step have already been executed")
    if not structural_invariant_holds:
        reasons.append("parsed source/destination did not match the live world state")
    if not reasons:
        return "Crane move rejected."
    return "Crane move rejected: " + "; ".join(reasons) + "."
