"""World simulation for the warehouse robot recovery scenario.

Monitors cumulative communication character usage per round and sends
real-time status notifications when time thresholds are crossed on the
shared radio channel. A round fails when the communication budget is
exceeded or the floor associate never calls ``perform_recovery`` with
an action the judge approves.
"""

import logging
from typing import NamedTuple

from glossogen.runtime.scenario_world import MessageEvent, ScenarioWorld, WorldContext
from glossogen.scenarios.warehouse_robot_recovery.ids import (
    BUDGET_EXCEEDED_MARKER,
    POSTMORTEM_CHANNEL_ID,
    RADIO_CHANNEL_ID,
    ROBOT_NOT_RECOVERED_MARKER,
    ROBOT_RECOVERED_MARKER,
)
from glossogen.scenarios.warehouse_robot_recovery.warehouse_cases import WarehouseCase

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"


class RecoveryOutcome(NamedTuple):
    """Result of a single warehouse recovery case after a round completes."""

    case_number: int
    robot_id: str
    recovered: bool
    judge_passed: bool
    budget_exceeded: bool
    characters_used: int
    time_elapsed_seconds: float
    time_budget_seconds: int
    fault_count: int
    judge_explanation: str


class WarehouseWorld(ScenarioWorld):
    """Monitors communication and pushes real-time status updates for the warehouse team.

    Tracks cumulative character count per round. When the simulated time
    crosses 75% of the round's budget or the budget is exceeded, broadcasts
    a critical or collapse notification to the radio channel. A round is
    considered recovered only if the floor associate's ``perform_recovery``
    call earns a positive judgment from the recovery judge before the
    budget runs out.
    """

    _context: WorldContext

    def __init__(
        self,
        cases: list[WarehouseCase],
        postmortem_globally_disabled: bool,
    ) -> None:
        self._cases = cases
        self._current_case: WarehouseCase | None = None
        self._in_postmortem: bool = False
        self._postmortem_globally_disabled: bool = postmortem_globally_disabled
        self._current_round_characters: int = 0
        self._round_recovered: bool = False
        self._round_judge_passed: bool = False
        self._round_budget_exceeded: bool = False
        self._round_outcome_marked: bool = False
        self._notified_thresholds: set[str] = set()
        self._outcomes: list[RecoveryOutcome] = []
        self._last_judge_explanation: str = ""

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def current_case(self) -> WarehouseCase | None:
        """The warehouse case for the current round."""
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
        """Running character count for the current round on the radio channel."""
        return self._current_round_characters

    @property
    def round_recovered(self) -> bool:
        """Whether the current round was successfully recovered."""
        return self._round_recovered

    @property
    def round_budget_exceeded(self) -> bool:
        """Whether the current round has exceeded its communication budget."""
        return self._round_budget_exceeded

    @property
    def outcomes(self) -> list[RecoveryOutcome]:
        """Historical per-round outcomes."""
        return self._outcomes

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

    def previous_outcome(self) -> RecoveryOutcome | None:
        """Return the most recent recorded outcome, or None when no rounds finished."""
        if len(self._outcomes) == 0:
            return None
        return self._outcomes[-1]

    async def record_recovery_judgment(
        self,
        judge_passed: bool,
        explanation: str,
    ) -> None:
        """Update world state after a ``perform_recovery`` judgment.

        Called from the scenario's tool executor. Sends a terminal status
        notification to the radio channel describing whether the round
        was recovered.
        """
        self._round_judge_passed = judge_passed
        self._last_judge_explanation = explanation
        if not judge_passed:
            await self._context.send_update_to_channel(
                channel_id=RADIO_CHANNEL_ID,
                text=f"{ROBOT_NOT_RECOVERED_MARKER}. The recovery action was rejected by review.",
            )
            return
        if self._round_budget_exceeded:
            await self._context.send_update_to_channel(
                channel_id=RADIO_CHANNEL_ID,
                text=(
                    f"{ROBOT_NOT_RECOVERED_MARKER}. "
                    "The recovery action was correct but the communication "
                    "budget was already exhausted."
                ),
            )
            return
        self._round_recovered = True
        await self._context.send_update_to_channel(
            channel_id=RADIO_CHANNEL_ID,
            text=f"{ROBOT_RECOVERED_MARKER}. The robot is back in a safe operating state.",
        )

    def mark_round_outcome(self, round_number: int) -> None:
        """Append the outcome for ``round_number`` (idempotent via guard)."""
        if self._round_outcome_marked:
            return
        self._mark_outcome(case_number=round_number)

    def finalize_round_sync(self, round_number: int) -> None:
        """Reset per-round state for the next case (back-fill any unmarked outcome).

        Called by the scenario's ``on_round_advanced`` before injections
        are delivered for the new round.
        """
        if round_number >= 2 and not self._round_outcome_marked:
            self._mark_outcome(case_number=round_number - 1)

        self._current_round_characters = 0
        self._round_recovered = False
        self._round_judge_passed = False
        self._round_budget_exceeded = False
        self._round_outcome_marked = False
        self._notified_thresholds = set()
        self._last_judge_explanation = ""

        case_index = (round_number - 1) % len(self._cases)
        self._current_case = self._cases[case_index]

    def _mark_outcome(self, case_number: int) -> None:
        """Append a RecoveryOutcome for the most recently completed round."""
        case = self._current_case
        if case is None:
            return
        self._outcomes.append(
            RecoveryOutcome(
                case_number=case_number,
                robot_id=case.robot_id,
                recovered=self._round_recovered,
                judge_passed=self._round_judge_passed,
                budget_exceeded=self._round_budget_exceeded,
                characters_used=self._current_round_characters,
                time_elapsed_seconds=float(self._current_round_characters),
                time_budget_seconds=case.time_budget_seconds,
                fault_count=len(case.faults),
                judge_explanation=self._last_judge_explanation,
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
        """Accumulate characters and update budget state synchronously.

        Called from ``send_message`` before the event is enqueued. Only
        messages on the radio channel count toward the budget; postmortem
        and any other channels are ignored.
        """
        _ = agent_id, token_count
        if channel_id != RADIO_CHANNEL_ID:
            return
        self._current_round_characters += len(text)
        if self._current_case is None:
            return
        if self._round_recovered:
            return
        if self._current_round_characters > self._current_case.time_budget_seconds:
            self._round_budget_exceeded = True

    async def on_message_async(self, event: MessageEvent, context: WorldContext) -> None:
        """React to an agent message: push budget/threshold notifications when relevant."""
        if event.channel_id != RADIO_CHANNEL_ID:
            return
        await self._send_threshold_notifications(context=context)

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
                channel_id=RADIO_CHANNEL_ID,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. "
                    f"Communication time: {time_elapsed:.0f}s "
                    f"({self._current_round_characters} chars) "
                    f"exceeded budget of {budget}s."
                ),
            )
            return
        if self._round_recovered:
            return
        if time_elapsed > budget * 0.75 and THRESHOLD_CRITICAL not in self._notified_thresholds:
            self._notified_thresholds.add(THRESHOLD_CRITICAL)
            remaining = budget - time_elapsed
            await context.send_update_to_channel(
                channel_id=RADIO_CHANNEL_ID,
                text=(f"CRITICAL: Recovery window narrowing. {remaining:.0f} seconds remaining."),
            )

    async def mark_round_failed_if_pending(self, reason: str) -> None:
        """Emit a terminal failure notification if the round did not recover.

        Called by the scenario at round-end so rounds ending via
        ``all_agents_idle`` or ``round_timeout`` still produce a terminal
        world event.
        """
        if self._round_recovered:
            return
        if THRESHOLD_BUDGET_EXCEEDED in self._notified_thresholds:
            return
        self._notified_thresholds.update([THRESHOLD_BUDGET_EXCEEDED, THRESHOLD_CRITICAL])
        await self._context.send_update_to_channel(
            channel_id=RADIO_CHANNEL_ID,
            text=f"{ROBOT_NOT_RECOVERED_MARKER}. {reason}",
        )
