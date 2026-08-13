"""World simulation for the warehouse robot recovery scenario.

Monitors cumulative communication character usage per round and sends
real-time status notifications when time thresholds are crossed on the
shared radio channel. A round fails when the communication budget is
exceeded or the floor associate never calls ``perform_recovery`` with
an action the judge approves.
"""

import logging
from typing import NamedTuple

from glossogen.engine.round_outcome_log import RoundOutcomeLog
from glossogen.engine.round_world import RoundWorld
from glossogen.engine.team_declaration import TeamSpec
from glossogen.runtime.scenario_world import MessageEvent, WorldContext
from glossogen.scenarios.warehouse_robot_recovery.ids import (
    BUDGET_EXCEEDED_MARKER,
    RADIO_CHANNEL_ID,
    ROBOT_NOT_RECOVERED_MARKER,
    ROBOT_RECOVERED_MARKER,
)
from glossogen.scenarios.warehouse_robot_recovery.team_declaration import TEAM_ID
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


class WarehouseWorld(RoundWorld):
    """Monitors communication and pushes real-time status updates for the warehouse team.

    Tracks cumulative character count per round. When the simulated time
    crosses 75% of the round's budget or the budget is exceeded, broadcasts
    a critical or collapse notification to the radio channel. A round is
    considered recovered only if the floor associate's ``perform_recovery``
    call earns a positive judgment from the recovery judge before the
    budget runs out.
    """

    def __init__(
        self,
        cases: list[WarehouseCase],
        team_specs: tuple[TeamSpec, ...],
        postmortem_channel_ids: frozenset[str],
        postmortem_globally_disabled: bool,
    ) -> None:
        super().__init__(
            team_specs=team_specs,
            round_budget_thresholds=(THRESHOLD_BUDGET_EXCEEDED, THRESHOLD_CRITICAL),
            postmortem_channel_ids=postmortem_channel_ids,
            postmortem_globally_disabled=postmortem_globally_disabled,
        )
        self._cases = cases
        self._current_case: WarehouseCase | None = None
        self._round_recovered: bool = False
        self._round_judge_passed: bool = False
        self._round_budget_exceeded: bool = False
        self._round_outcome_marked: bool = False
        self._outcome_log: RoundOutcomeLog[RecoveryOutcome] = RoundOutcomeLog(team_ids=(TEAM_ID,))
        self._last_judge_explanation: str = ""

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._world_context

    @property
    def current_case(self) -> WarehouseCase | None:
        """The warehouse case for the current round."""
        return self._current_case

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
        return self._outcome_log.all_for(team_id=TEAM_ID)

    def previous_outcome(self) -> RecoveryOutcome | None:
        """Return the most recent recorded outcome, or None when no rounds finished."""
        recorded = self._outcome_log.all_for(team_id=TEAM_ID)
        if not recorded:
            return None
        return recorded[-1]

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
            await self._world_context.send_update_to_channel(
                channel_id=RADIO_CHANNEL_ID,
                text=f"{ROBOT_NOT_RECOVERED_MARKER}. The recovery action was rejected by review.",
            )
            return
        if self._round_budget_exceeded:
            await self._world_context.send_update_to_channel(
                channel_id=RADIO_CHANNEL_ID,
                text=(
                    f"{ROBOT_NOT_RECOVERED_MARKER}. "
                    "The recovery action was correct but the communication "
                    "budget was already exhausted."
                ),
            )
            return
        self._round_recovered = True
        await self._world_context.send_update_to_channel(
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

        # After the outcome above, which reads the round that just ended.
        self.begin_round()
        self._round_recovered = False
        self._round_judge_passed = False
        self._round_budget_exceeded = False
        self._round_outcome_marked = False
        self._last_judge_explanation = ""

        case_index = (round_number - 1) % len(self._cases)
        self._current_case = self._cases[case_index]

    def _mark_outcome(self, case_number: int) -> None:
        """Append a RecoveryOutcome for the most recently completed round."""
        case = self._current_case
        if case is None:
            return
        self._outcome_log.record(
            team_id=TEAM_ID,
            round_number=case_number,
            outcome=RecoveryOutcome(
                case_number=case_number,
                robot_id=case.robot_id,
                recovered=self._round_recovered,
                judge_passed=self._round_judge_passed,
                budget_exceeded=self._round_budget_exceeded,
                characters_used=self.characters_used(team_id=TEAM_ID),
                time_elapsed_seconds=float(self.characters_used(team_id=TEAM_ID)),
                time_budget_seconds=case.time_budget_seconds,
                fault_count=len(case.faults),
                judge_explanation=self._last_judge_explanation,
            ),
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
        super().on_message(
            agent_id=agent_id, channel_id=channel_id, text=text, token_count=token_count
        )
        if self.team_for_task_channel(channel_id=channel_id) is None:
            return
        if self._current_case is None:
            return
        if self._round_recovered:
            return
        if self.characters_used(team_id=TEAM_ID) > self._current_case.time_budget_seconds:
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
        time_elapsed = self.characters_used(team_id=TEAM_ID)
        budget = self._current_case.time_budget_seconds

        if self._round_budget_exceeded and self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=THRESHOLD_BUDGET_EXCEEDED
        ):
            await context.send_update_to_channel(
                channel_id=RADIO_CHANNEL_ID,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. "
                    f"Communication time: {time_elapsed:.0f}s "
                    f"({self.characters_used(team_id=TEAM_ID)} chars) "
                    f"exceeded budget of {budget}s."
                ),
            )
            return
        if self._round_recovered:
            return
        if time_elapsed > budget * 0.75 and self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=THRESHOLD_CRITICAL
        ):
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
        if not self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=THRESHOLD_BUDGET_EXCEEDED
        ):
            return
        await self._world_context.send_update_to_channel(
            channel_id=RADIO_CHANNEL_ID,
            text=f"{ROBOT_NOT_RECOVERED_MARKER}. {reason}",
        )
