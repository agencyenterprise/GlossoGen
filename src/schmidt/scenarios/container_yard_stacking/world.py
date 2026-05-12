"""World simulation for the container_yard_stacking scenario.

Tracks the four-stack yard state, the truck's destination, the
per-round running character count on the coordination channel, and the
crane-move history. The world is mutated synchronously by the two
scenario tools: the truck judge writes into ``record_truck_destination``
and the crane judge writes into ``record_crane_move``. Round success is
deterministic: the truck must arrive at the correct crane spot, the
incoming container must end at its target position, and the
communication budget must not have been exceeded.
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
from schmidt.scenarios.container_yard_stacking.ids import (
    BAY_NAME,
    BLOCK_NAME,
    BUDGET_EXCEEDED_MARKER,
    CONTAINER_PLACED_MARKER,
    COORDINATION_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    ROUND_FAILED_MARKER,
    ROUND_SUCCESS_MARKER,
    TRUCK_ARRIVED_MARKER,
    TRUCK_WRONG_SPOT_MARKER,
)
from schmidt.scenarios.container_yard_stacking.yard_cases import CraneMoveStep, YardCase

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"


class YardOutcome(NamedTuple):
    """Result of a single yard case after a round completes."""

    case_number: int
    incoming_container_id: str
    target_position_text: str
    expected_move_count: int
    accepted_move_count: int
    truck_arrived_at_correct_spot: bool
    truck_text: str
    target_placed: bool
    budget_exceeded: bool
    characters_used: int
    time_budget_seconds: int
    round_succeeded: bool
    failure_reason: str


class ContainerYardWorld(ScenarioWorld):
    """Living-yard world that judges truck routing and crane moves deterministically."""

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
        self._current_temp_slots: dict[str, str | None] = {}
        self._truck_destination_text: str | None = None
        self._truck_arrived_at_correct_spot: bool = False
        self._truck_judged: bool = False
        self._accepted_moves: list[CraneMoveStep] = []
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
        """Running character count for the current round on the coordination channel."""
        return self._current_round_characters

    @property
    def round_budget_exceeded(self) -> bool:
        """Whether the current round has exceeded its communication budget."""
        return self._round_budget_exceeded

    @property
    def truck_judged(self) -> bool:
        """Whether the truck destination has been judged this round."""
        return self._truck_judged

    @property
    def truck_arrived_at_correct_spot(self) -> bool:
        """Whether the truck arrived at the correct crane station and pad."""
        return self._truck_arrived_at_correct_spot

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

    def render_world_snapshot(self) -> str:
        """Render the current stack and temp-slot state as a compact human-readable string.

        Used by ``judge_crane_move`` to ground its physical-accessibility
        check in the world's actual current state.
        """
        case = self._current_case
        if case is None:
            return "no active case"
        lines: list[str] = []
        for stack_index in sorted(self._current_stacks.keys()):
            contents = self._current_stacks[stack_index]
            if len(contents) == 0:
                lines.append(f"Stack {stack_index}: empty")
            else:
                tiers = ", ".join(
                    f"Tier {tier_idx} = {container_id}"
                    for tier_idx, container_id in enumerate(contents, start=1)
                )
                lines.append(f"Stack {stack_index}: {tiers}")
        for slot_name in case.temp_slot_names:
            occupant = self._current_temp_slots.get(slot_name)
            if occupant is None:
                lines.append(f"{slot_name}: empty")
            else:
                lines.append(f"{slot_name}: {occupant}")
        truck_container = self._truck_container_id()
        if truck_container is None:
            lines.append("Truck: empty")
        else:
            lines.append(f"Truck carries: {truck_container}")
        return "\n".join(lines)

    def _truck_container_id(self) -> str | None:
        """Return the incoming container id if it has not yet been placed by the crane."""
        case = self._current_case
        if case is None:
            return None
        if self._target_placed:
            return None
        return case.incoming_container.container_id

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

    async def record_truck_destination(
        self,
        targets_correct_station: bool,
        targets_correct_pad: bool,
        carries_correct_container: bool,
        submitted_destination_text: str,
    ) -> bool:
        """Update world state after the truck judge rules on a destination."""
        self._truck_judged = True
        self._truck_destination_text = submitted_destination_text
        all_correct = targets_correct_station and targets_correct_pad and carries_correct_container
        self._truck_arrived_at_correct_spot = all_correct
        if all_correct:
            await self._context.send_update_to_channel(
                channel_id=COORDINATION_CHANNEL_ID,
                text=(
                    f"{TRUCK_ARRIVED_MARKER}. The truck is positioned at the correct "
                    "crane transfer pad and is ready for the crane to begin."
                ),
            )
            return True
        self._round_failed_terminally = True
        self._failure_reason = "Truck arrived at the wrong crane spot."
        await self._context.send_update_to_channel(
            channel_id=COORDINATION_CHANNEL_ID,
            text=(
                f"{TRUCK_WRONG_SPOT_MARKER}. The truck did not arrive at the correct "
                "crane station, pad, or with the correct container. The round cannot recover."
            ),
        )
        return False

    async def record_crane_move(
        self,
        parsed_move: CraneMoveStep,
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
        accepted = (
            matches_expected_next_move
            and source_currently_holds_container
            and destination_currently_empty
            and not self._round_failed_terminally
            and self.accepted_move_count < len(case.expected_move_sequence)
            and self._truck_arrived_at_correct_spot
        )
        if not accepted:
            self._round_failed_terminally = True
            self._failure_reason = "A crane move was rejected by the world."
            return False
        self._apply_move_to_state(parsed_move=parsed_move)
        self._accepted_moves.append(parsed_move)
        if (
            parsed_move.destination
            == _stack_position_text(
                stack=case.target_position.stack,
                tier=case.target_position.tier,
            )
            and parsed_move.container_id == case.incoming_container.container_id
        ):
            self._target_placed = True
            await self._context.send_update_to_channel(
                channel_id=COORDINATION_CHANNEL_ID,
                text=(
                    f"{CONTAINER_PLACED_MARKER}. {parsed_move.container_id} is now "
                    f"at {parsed_move.destination}."
                ),
            )
        return True

    def _apply_move_to_state(self, parsed_move: CraneMoveStep) -> None:
        """Mutate the stack and temp-slot state to reflect an accepted move."""
        case = self._current_case
        if case is None:
            return
        source = parsed_move.source
        destination = parsed_move.destination
        container_id = parsed_move.container_id
        if source.startswith("truck at"):
            pass
        elif source in case.temp_slot_names:
            self._current_temp_slots[source] = None
        else:
            stack_index = _stack_index_from_text(text=source)
            if stack_index is not None and len(self._current_stacks[stack_index]) > 0:
                self._current_stacks[stack_index].pop()
        if destination in case.temp_slot_names:
            self._current_temp_slots[destination] = container_id
        else:
            stack_index = _stack_index_from_text(text=destination)
            if stack_index is not None:
                self._current_stacks[stack_index].append(container_id)

    def finalize_round_sync(self, round_number: int) -> None:
        """Compute the previous round's outcome and reset per-round state for the next case."""
        if round_number >= 2 and not self._round_outcome_marked:
            self._mark_outcome(case_number=round_number - 1)
        self._current_round_characters = 0
        self._round_budget_exceeded = False
        self._notified_thresholds = set()
        self._truck_destination_text = None
        self._truck_arrived_at_correct_spot = False
        self._truck_judged = False
        self._accepted_moves = []
        self._target_placed = False
        self._round_failed_terminally = False
        self._failure_reason = ""
        self._round_outcome_marked = False
        case_index = (round_number - 1) % len(self._cases)
        next_case = self._cases[case_index]
        self._current_case = next_case
        self._current_stacks = {
            stack_index: list(containers)
            for stack_index, containers in next_case.initial_stacks.items()
        }
        self._current_temp_slots = {slot: None for slot in next_case.temp_slot_names}

    def _mark_outcome(self, case_number: int) -> None:
        """Append a YardOutcome for the most recently completed round."""
        case = self._current_case
        if case is None:
            return
        round_succeeded = (
            self._truck_arrived_at_correct_spot
            and self._target_placed
            and not self._round_budget_exceeded
            and not self._round_failed_terminally
            and self.accepted_move_count == len(case.expected_move_sequence)
        )
        target_text = _stack_position_text(
            stack=case.target_position.stack,
            tier=case.target_position.tier,
        )
        truck_text = self._truck_destination_text or ""
        self._outcomes.append(
            YardOutcome(
                case_number=case_number,
                incoming_container_id=case.incoming_container.container_id,
                target_position_text=target_text,
                expected_move_count=len(case.expected_move_sequence),
                accepted_move_count=self.accepted_move_count,
                truck_arrived_at_correct_spot=self._truck_arrived_at_correct_spot,
                truck_text=truck_text,
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
        if channel_id != COORDINATION_CHANNEL_ID:
            return
        self._current_round_characters += len(text)
        if self._current_case is None:
            return
        if self._current_round_characters > self._current_case.time_budget_seconds:
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
                    if event.channel_id != COORDINATION_CHANNEL_ID:
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
                channel_id=COORDINATION_CHANNEL_ID,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. Communication time: "
                    f"{time_elapsed} chars exceeded budget of {budget}s."
                ),
            )
            return
        if time_elapsed > budget * 0.75 and THRESHOLD_CRITICAL not in self._notified_thresholds:
            self._notified_thresholds.add(THRESHOLD_CRITICAL)
            remaining = budget - time_elapsed
            await context.send_update_to_channel(
                channel_id=COORDINATION_CHANNEL_ID,
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
        round_succeeded = (
            self._truck_arrived_at_correct_spot
            and self._target_placed
            and not self._round_budget_exceeded
            and not self._round_failed_terminally
            and self.accepted_move_count == len(case.expected_move_sequence)
        )
        if round_succeeded:
            text = f"{ROUND_SUCCESS_MARKER}. Container placed correctly within budget."
        else:
            reason = (
                self._failure_reason
                if self._failure_reason != ""
                else "Round did not complete the placement."
            )
            text = f"{ROUND_FAILED_MARKER}. {reason}"
        await self._context.send_update_to_channel(
            channel_id=COORDINATION_CHANNEL_ID,
            text=text,
        )


def _stack_position_text(stack: int, tier: int) -> str:
    """Return the canonical "Block Delta, Bay Seven, Stack S, Tier T" string."""
    return f"{BLOCK_NAME}, {BAY_NAME}, Stack {stack}, Tier {tier}"


def _stack_index_from_text(text: str) -> int | None:
    """Parse "Block Delta, Bay Seven, Stack S, Tier T" and return S, or None on mismatch."""
    for token in text.split(","):
        token = token.strip()
        if token.lower().startswith("stack "):
            tail = token[len("Stack ") :].strip()
            try:
                return int(tail)
            except ValueError:
                return None
    return None
