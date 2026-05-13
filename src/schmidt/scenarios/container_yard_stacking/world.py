"""World simulation for the container_yard_stacking scenario.

Tracks the four-stack yard state, the per-truck positions and contents
(inbound truck always; outbound truck whenever the round needs a
blocker moved aside), the per-round running character count on the link
channel, and the crane-move history. The world is mutated synchronously
by the two scenario tools: structured ``move_truck`` args feed
``record_truck_commit`` and structured ``crane_move`` args feed
``record_crane_move``. Round success is deterministic: every expected
truck must arrive at the correct spot, the expected crane plan must
complete on the live world state, and the communication budget must not
have been exceeded.
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
from schmidt.scenarios.container_yard_stacking.events import ContainerYardCraneMoveStep
from schmidt.scenarios.container_yard_stacking.ids import (
    BUDGET_EXCEEDED_MARKER,
    CONTAINER_PLACED_MARKER,
    INBOUND_TRUCK_ROLE,
    LINK_CHANNEL_ID,
    OUTBOUND_TRUCK_ROLE,
    POSTMORTEM_CHANNEL_ID,
    ROUND_FAILED_MARKER,
    ROUND_SUCCESS_MARKER,
    TRUCK_ARRIVED_MARKER,
    TRUCK_WRONG_SPOT_MARKER,
)
from schmidt.scenarios.container_yard_stacking.yard_cases import TruckAssignment, YardCase

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"


class TruckState(NamedTuple):
    """Live per-round position and contents of one truck."""

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


class YardOutcome(NamedTuple):
    """Result of a single yard case after a round completes."""

    case_number: int
    incoming_container_id: str
    target_position_text: str
    expected_move_count: int
    accepted_move_count: int
    trucks_arrived_at_correct_spot: bool
    expected_truck_count: int
    correctly_committed_truck_count: int
    target_placed: bool
    budget_exceeded: bool
    characters_used: int
    time_budget_seconds: int
    round_succeeded: bool
    failure_reason: str


class ContainerYardWorld(ScenarioWorld):
    """Living-yard world that judges truck commits and crane moves deterministically."""

    _context: WorldContext

    def __init__(
        self,
        cases: list[YardCase],
        postmortem_globally_disabled: bool,
    ) -> None:
        self._cases = cases
        self._current_case: YardCase | None = None
        self._in_postmortem: bool = False
        self._postmortem_globally_disabled: bool = postmortem_globally_disabled
        self._current_round_characters: int = 0
        self._round_budget_exceeded: bool = False
        self._notified_thresholds: set[str] = set()
        self._outcomes: list[YardOutcome] = []
        self._current_stacks: dict[int, list[str]] = {}
        self._truck_states: dict[str, TruckState] = {}
        self._accepted_moves: list[ContainerYardCraneMoveStep] = []
        self._target_placed: bool = False
        self._round_failed_terminally: bool = False
        self._failure_reason: str = ""
        self._round_outcome_marked: bool = False

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def current_case(self) -> YardCase | None:
        """The yard case for the current round."""
        return self._current_case

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is in a postmortem discussion phase."""
        return self._in_postmortem

    @property
    def is_postmortem_disabled(self) -> bool:
        """Whether postmortem has been globally disabled."""
        return self._postmortem_globally_disabled

    @property
    def current_round_characters(self) -> int:
        """Running character count for the current round on the link channel."""
        return self._current_round_characters

    @property
    def round_budget_exceeded(self) -> bool:
        """Whether the current round has exceeded its communication budget."""
        return self._round_budget_exceeded

    @property
    def accepted_move_count(self) -> int:
        """Number of crane moves accepted so far this round."""
        return len(self._accepted_moves)

    @property
    def target_placed(self) -> bool:
        """Whether the incoming container has been placed at its target slot."""
        return self._target_placed

    @property
    def round_failed_terminally(self) -> bool:
        """Whether the current round has been marked unrecoverable."""
        return self._round_failed_terminally

    @property
    def outcomes(self) -> list[YardOutcome]:
        """Historical per-round outcomes."""
        return self._outcomes

    def all_trucks_arrived_correctly(self) -> bool:
        """Whether every expected truck for this round has arrived at the correct spot.

        A truck counts as correctly arrived when it is parked at the
        correct station's pads (any pad chosen by the planner) and the
        world accepted the commitment. The planner-chosen pad is recorded
        in ``truck_states[role].pad`` at commit time; we treat any
        non-empty pad here as valid because ``record_truck_commit`` only
        stores accepted commits.
        """
        case = self._current_case
        if case is None:
            return False
        for assignment in case.truck_assignments:
            state = self._truck_states.get(assignment.truck_role)
            if state is None or not state.arrived:
                return False
            if state.station_name != assignment.station_name:
                return False
            if state.pad == "":
                return False
        return True

    def truck_arrived(self, truck_role: str) -> bool:
        """Whether the named truck role has arrived at its correct spot this round."""
        state = self._truck_states.get(truck_role)
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
        """Postmortem channel when disabled."""
        if not self._postmortem_globally_disabled:
            return frozenset()
        return frozenset({POSTMORTEM_CHANNEL_ID})

    def previous_outcome(self) -> YardOutcome | None:
        """Return the most recent recorded outcome, or None when no rounds finished."""
        if len(self._outcomes) == 0:
            return None
        return self._outcomes[-1]

    def find_assignment(self, truck_role: str) -> TruckAssignment | None:
        """Return the ground-truth assignment for ``truck_role`` this round, if any."""
        case = self._current_case
        if case is None:
            return None
        for assignment in case.truck_assignments:
            if assignment.truck_role == truck_role:
                return assignment
        return None

    async def record_truck_commit(
        self,
        parsed_truck_role: str,
        parsed_pad: str,
        role_matches_active_assignment: bool,
        targets_correct_station: bool,
        targets_correct_pad: bool,
        carries_correct_container: bool,
    ) -> TruckCommitResult:
        """Update world state with the verdict for one ``move_truck`` call.

        ``parsed_pad`` is the canonical pad string resolved from the
        operator's structured ``move_truck`` argument; it is stored in
        ``truck_states[role].pad`` when the commit is accepted so
        subsequent crane-move validation can reference it.
        """
        case = self._current_case
        if case is None:
            return TruckCommitResult(
                truck_role=parsed_truck_role,
                accepted=False,
                duplicate=False,
            )
        if parsed_truck_role in self._truck_states:
            return TruckCommitResult(
                truck_role=parsed_truck_role,
                accepted=False,
                duplicate=True,
            )
        assignment = self.find_assignment(truck_role=parsed_truck_role)
        pad_already_used = parsed_pad != "" and parsed_pad in self.pads_already_committed()
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
            self._round_failed_terminally = True
            reason = _truck_failure_reason(
                parsed_truck_role=parsed_truck_role,
                role_matches_active_assignment=role_matches_active_assignment,
                targets_correct_station=targets_correct_station,
                targets_correct_pad=targets_correct_pad,
                carries_correct_container=carries_correct_container,
                role_known=role_known,
                pad_already_used=pad_already_used,
            )
            if self._failure_reason == "":
                self._failure_reason = reason
            self._truck_states[parsed_truck_role] = TruckState(
                truck_role=parsed_truck_role,
                arrived=False,
                station_name="",
                pad="",
                container_id="",
            )
            await self._context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=f"{parsed_truck_role.upper()} {TRUCK_WRONG_SPOT_MARKER}. {reason}",
            )
            return TruckCommitResult(
                truck_role=parsed_truck_role,
                accepted=False,
                duplicate=False,
            )
        accepted_assignment = assignment
        assert accepted_assignment is not None  # narrowed by the all_correct check above
        self._truck_states[parsed_truck_role] = TruckState(
            truck_role=parsed_truck_role,
            arrived=True,
            station_name=accepted_assignment.station_name,
            pad=parsed_pad,
            container_id=accepted_assignment.container_id,
        )
        await self._context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
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

    def pads_already_committed(self) -> list[str]:
        """Return non-empty pads currently bound to a truck this round."""
        return [
            state.pad for state in self._truck_states.values() if state.arrived and state.pad != ""
        ]

    def source_holds_container(self, kind: str, stack: int | None, container_id: str) -> bool:
        """Return True when the named source currently carries ``container_id``."""
        if kind == "inbound_truck":
            state = self._truck_states.get(INBOUND_TRUCK_ROLE)
            return state is not None and state.arrived and state.container_id == container_id
        if kind == "outbound_truck":
            state = self._truck_states.get(OUTBOUND_TRUCK_ROLE)
            return state is not None and state.arrived and state.container_id == container_id
        if kind == "stack_tier":
            if stack is None or stack not in self._current_stacks:
                return False
            contents = self._current_stacks[stack]
            return len(contents) > 0 and contents[-1] == container_id
        return False

    def destination_is_free(self, kind: str, stack: int | None, tier: int | None) -> bool:
        """Return True when the named destination is currently free for a crane drop."""
        if kind == "inbound_truck":
            return False
        if kind == "outbound_truck":
            state = self._truck_states.get(OUTBOUND_TRUCK_ROLE)
            return state is not None and state.arrived and state.container_id == ""
        if kind == "stack_tier":
            if stack is None or stack not in self._current_stacks or tier is None:
                return False
            return tier == len(self._current_stacks[stack]) + 1
        return False

    def last_failure_reason(self) -> str:
        """Return the most recently recorded failure reason for this round."""
        if self._failure_reason == "":
            return "Crane move rejected."
        return self._failure_reason

    async def record_crane_move(
        self,
        parsed_move: ContainerYardCraneMoveStep,
        parsed_source_kind: str,
        parsed_source_stack: int | None,
        parsed_destination_kind: str,
        parsed_destination_stack: int | None,
        matches_expected_next_move: bool,
        source_currently_holds_container: bool,
        destination_currently_empty: bool,
    ) -> bool:
        """Apply or reject a crane move and emit the appropriate world notification.

        Returns True when the move was accepted (stacks mutated, world
        notification with success marker emitted). Returns False otherwise and
        marks the round as terminally failed.
        """
        case = self._current_case
        if case is None:
            return False
        round_already_failed = self._round_failed_terminally
        sequence_already_exhausted = self.accepted_move_count >= len(case.expected_move_sequence)
        structural_invariant_holds = self._structural_invariants_hold(
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
            self._round_failed_terminally = True
            reason = _crane_failure_reason(
                matches_expected_next_move=matches_expected_next_move,
                source_currently_holds_container=source_currently_holds_container,
                destination_currently_empty=destination_currently_empty,
                round_already_failed=round_already_failed,
                sequence_already_exhausted=sequence_already_exhausted,
                structural_invariant_holds=structural_invariant_holds,
            )
            if self._failure_reason == "":
                self._failure_reason = reason
            return False
        self._apply_move_to_state(
            parsed_move=parsed_move,
            source_kind=parsed_source_kind,
            source_stack=parsed_source_stack,
            destination_kind=parsed_destination_kind,
            destination_stack=parsed_destination_stack,
        )
        self._accepted_moves.append(parsed_move)
        if self._incoming_container_at_target():
            self._target_placed = True
            target_text = _stack_position_text(
                stack=case.target_position.stack,
                tier=case.target_position.tier,
            )
            await self._context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=(
                    f"{CONTAINER_PLACED_MARKER}. {case.incoming_container_id} "
                    f"is now at {target_text}."
                ),
            )
        return True

    def _structural_invariants_hold(
        self,
        container_id: str,
        source_kind: str,
        source_stack: int | None,
        destination_kind: str,
        destination_stack: int | None,
    ) -> bool:
        """Verify the parsed move's structural invariants against live world state.

        Catches parsed-arg inconsistencies that would otherwise silently
        corrupt the world's stack state. Run before ``_apply_move_to_state``
        mutates anything, so a False here flips the move to a clean
        rejection instead of forging ahead with a wrong pop/push. Also
        enforces the scenario's directional vocabulary: ``inbound_truck``
        is only valid as a source, ``outbound_truck`` is only valid as a
        destination.
        """
        if source_kind == "outbound_truck":
            return False
        if destination_kind == "inbound_truck":
            return False
        if source_kind == "inbound_truck":
            state = self._truck_states.get(INBOUND_TRUCK_ROLE)
            if state is None or not state.arrived or state.container_id != container_id:
                return False
        elif source_kind == "stack_tier":
            if source_stack is None or source_stack not in self._current_stacks:
                return False
            stack_contents = self._current_stacks[source_stack]
            if len(stack_contents) == 0 or stack_contents[-1] != container_id:
                return False
        else:
            return False
        if destination_kind == "outbound_truck":
            state = self._truck_states.get(OUTBOUND_TRUCK_ROLE)
            if state is None or not state.arrived or state.container_id != "":
                return False
        elif destination_kind == "stack_tier":
            if destination_stack is None or destination_stack not in self._current_stacks:
                return False
        else:
            return False
        return True

    def _incoming_container_at_target(self) -> bool:
        """Return True when the live world state has the incoming container at the target slot.

        Reads ``self._current_stacks`` directly, so the check is grounded
        in the world's mutated state rather than the rendered
        ``parsed_move.destination`` string.
        """
        case = self._current_case
        if case is None:
            return False
        stack_contents = self._current_stacks.get(case.target_position.stack)
        if stack_contents is None:
            return False
        if len(stack_contents) < case.target_position.tier:
            return False
        tier_index = case.target_position.tier - 1
        return stack_contents[tier_index] == case.incoming_container_id

    def _apply_move_to_state(
        self,
        parsed_move: ContainerYardCraneMoveStep,
        source_kind: str,
        source_stack: int | None,
        destination_kind: str,
        destination_stack: int | None,
    ) -> None:
        """Mutate the stack and truck state to reflect an accepted move.

        Caller (``record_crane_move``) must have already verified
        ``_structural_invariants_hold`` so every branch here can mutate
        without re-checking ranges or top-of-stack identity.
        """
        container_id = parsed_move.container_id
        if source_kind == "inbound_truck":
            self._unload_truck(truck_role=INBOUND_TRUCK_ROLE)
        elif source_kind == "stack_tier":
            assert source_stack is not None
            self._current_stacks[source_stack].pop()
        if destination_kind == "outbound_truck":
            self._load_truck(truck_role=OUTBOUND_TRUCK_ROLE, container_id=container_id)
        elif destination_kind == "stack_tier":
            assert destination_stack is not None
            self._current_stacks[destination_stack].append(container_id)

    def _unload_truck(self, truck_role: str) -> None:
        """Mark ``truck_role`` as empty in the live world state."""
        state = self._truck_states.get(truck_role)
        if state is None:
            return
        self._truck_states[truck_role] = state._replace(container_id="")

    def _load_truck(self, truck_role: str, container_id: str) -> None:
        """Mark ``truck_role`` as carrying ``container_id`` in the live world state."""
        state = self._truck_states.get(truck_role)
        if state is None:
            return
        self._truck_states[truck_role] = state._replace(container_id=container_id)

    def mark_round_outcome(self, round_number: int) -> None:
        """Append the outcome for ``round_number`` to the outcomes list.

        Idempotent — safe to call from both ``on_round_ended`` (so the
        postmortem injection can read the just-ended round's result) and
        ``finalize_round_sync`` (defensive fallback). The
        ``_round_outcome_marked`` guard prevents double-marking.
        """
        if self._round_outcome_marked:
            return
        self._mark_outcome(case_number=round_number)

    def finalize_round_sync(self, round_number: int) -> None:
        """Reset per-round state for the next case (and back-fill any unmarked outcome)."""
        assert (
            1 <= round_number <= len(self._cases)
        ), f"round_number {round_number} out of range [1, {len(self._cases)}]"
        if round_number >= 2 and not self._round_outcome_marked:
            self._mark_outcome(case_number=round_number - 1)
        self._current_round_characters = 0
        self._round_budget_exceeded = False
        self._notified_thresholds = set()
        self._truck_states = {}
        self._accepted_moves = []
        self._target_placed = False
        self._round_failed_terminally = False
        self._failure_reason = ""
        self._round_outcome_marked = False
        next_case = self._cases[round_number - 1]
        self._current_case = next_case
        self._current_stacks = {
            stack_index: list(containers)
            for stack_index, containers in next_case.initial_stacks.items()
        }

    def _round_succeeded(self) -> bool:
        """Return True when every success criterion for the current round is met."""
        case = self._current_case
        if case is None:
            return False
        return (
            self.all_trucks_arrived_correctly()
            and self._target_placed
            and not self._round_budget_exceeded
            and not self._round_failed_terminally
            and self.accepted_move_count == len(case.expected_move_sequence)
        )

    def _mark_outcome(self, case_number: int) -> None:
        """Append a YardOutcome for the most recently completed round."""
        case = self._current_case
        if case is None:
            return
        all_trucks_correct = self.all_trucks_arrived_correctly()
        round_succeeded = self._round_succeeded()
        target_text = _stack_position_text(
            stack=case.target_position.stack,
            tier=case.target_position.tier,
        )
        correctly_committed = sum(
            1
            for assignment in case.truck_assignments
            if (
                (state := self._truck_states.get(assignment.truck_role)) is not None
                and state.arrived
                and state.station_name == assignment.station_name
                and state.pad != ""
            )
        )
        self._outcomes.append(
            YardOutcome(
                case_number=case_number,
                incoming_container_id=case.incoming_container_id,
                target_position_text=target_text,
                expected_move_count=len(case.expected_move_sequence),
                accepted_move_count=self.accepted_move_count,
                trucks_arrived_at_correct_spot=all_trucks_correct,
                expected_truck_count=len(case.truck_assignments),
                correctly_committed_truck_count=correctly_committed,
                target_placed=self._target_placed,
                budget_exceeded=self._round_budget_exceeded,
                characters_used=self._current_round_characters,
                time_budget_seconds=case.time_budget_seconds,
                round_succeeded=round_succeeded,
                failure_reason=self._failure_reason,
            )
        )
        self._round_outcome_marked = True

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate characters and update budget state synchronously."""
        _ = agent_id, token_count
        if channel_id != LINK_CHANNEL_ID:
            return
        self._current_round_characters += len(text)
        if self._current_case is None:
            return
        if self._current_round_characters >= self._current_case.time_budget_seconds:
            self._round_budget_exceeded = True
            self._round_failed_terminally = True
            if self._failure_reason == "":
                self._failure_reason = "Communication budget exhausted."

    async def run(self, context: WorldContext) -> None:
        """Process events and send async notifications for threshold crossings."""
        self._context = context
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    continue
                if isinstance(event, MessageEvent):
                    if event.channel_id != LINK_CHANNEL_ID:
                        continue
                    await self._send_threshold_notifications(context=context)
        except asyncio.CancelledError:
            return

    async def _send_threshold_notifications(self, context: WorldContext) -> None:
        """Send status notifications when budget thresholds are crossed."""
        if self._current_case is None:
            return
        time_elapsed = self._current_round_characters
        budget = self._current_case.time_budget_seconds
        if (
            self._round_budget_exceeded
            and THRESHOLD_BUDGET_EXCEEDED not in self._notified_thresholds
        ):
            self._notified_thresholds.update([THRESHOLD_BUDGET_EXCEEDED, THRESHOLD_CRITICAL])
            await context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. Communication time: "
                    f"{time_elapsed} chars exceeded budget of {budget}s."
                ),
            )
            return
        if time_elapsed >= budget * 0.75 and THRESHOLD_CRITICAL not in self._notified_thresholds:
            self._notified_thresholds.add(THRESHOLD_CRITICAL)
            remaining = budget - time_elapsed
            await context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=f"CRITICAL: Yard window narrowing. {remaining} seconds of budget remaining.",
            )

    async def emit_round_terminal_notification(self) -> None:
        """Emit the per-round success or failure marker for the metric to pick up.

        Called by the scenario at round-end so every round closes with one
        unambiguous notification carrying ``ROUND_SUCCESS_MARKER`` or
        ``ROUND_FAILED_MARKER``.
        """
        case = self._current_case
        if case is None:
            return
        if self._round_succeeded():
            text = f"{ROUND_SUCCESS_MARKER}. Container placed correctly within budget."
        else:
            if self._failure_reason != "":
                reason = self._failure_reason
            else:
                reason = "Round did not complete the placement."
            text = f"{ROUND_FAILED_MARKER}. {reason}"
        await self._context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
            text=text,
        )


def _stack_position_text(stack: int, tier: int) -> str:
    """Return the canonical "Stack S, Tier T" position string."""
    return f"Stack {stack}, Tier {tier}"


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
        reasons.append("role does not match any active assignment for this round")
    elif not role_known:
        reasons.append(f"no assignment matches the parsed role {parsed_truck_role!r}")
    if not targets_correct_station:
        reasons.append("destination text does not identify the correct crane station")
    if not targets_correct_pad:
        reasons.append("destination pad is not a free pad at the correct station")
    if not carries_correct_container:
        reasons.append("inbound text does not name the correct incoming container")
    if pad_already_used:
        reasons.append("destination pad is already used by another truck this round")
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
        reasons.append("all expected crane moves have already been executed")
    if not structural_invariant_holds:
        reasons.append("parsed source/destination did not match the live world state")
    if not reasons:
        return "Crane move rejected."
    return "Crane move rejected: " + "; ".join(reasons) + "."
