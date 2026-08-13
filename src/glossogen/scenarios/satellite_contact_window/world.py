"""World simulation for the satellite contact window scenario.

Monitors cumulative communication character usage per round and sends
real-time status notifications when the contact-window budget is crossed
on the shared ``link`` channel. A round fails when the contact window
closes or the operator never calls ``send_command_sequence`` with a
sequence the judge approves.
"""

import logging
from typing import NamedTuple

from glossogen.engine.round_outcome_log import RoundOutcomeLog
from glossogen.engine.round_world import RoundWorld
from glossogen.engine.team_declaration import TeamSpec
from glossogen.runtime.scenario_world import MessageEvent, WorldContext
from glossogen.scenarios.satellite_contact_window.cases import CommandStep, SatelliteCase
from glossogen.scenarios.satellite_contact_window.ids import (
    COMMAND_ACCEPTED_MARKER,
    COMMAND_REJECTED_MARKER,
    CONTACT_WINDOW_CLOSED_MARKER,
    CONTACT_WINDOW_CRITICAL_MARKER,
    LINK_CHANNEL_ID,
    SATELLITE_NOT_RECOVERED_MARKER,
    SATELLITE_RECOVERED_MARKER,
)
from glossogen.scenarios.satellite_contact_window.team_declaration import TEAM_ID

logger = logging.getLogger(__name__)

THRESHOLD_WINDOW_CLOSED = "window_closed"
THRESHOLD_CRITICAL = "critical"


class SatelliteOutcome(NamedTuple):
    """Result of a single satellite contact-window case after a round completes."""

    case_number: int
    pattern_name: str
    recovered: bool
    judge_passed: bool
    window_closed: bool
    characters_used: int
    time_elapsed_seconds: float
    round_time_budget_seconds: int
    pattern_count: int
    submitted_sequence: tuple[CommandStep, ...]
    violations: tuple[str, ...]
    judge_explanation: str


class SatelliteWorld(RoundWorld):
    """Monitors communication and pushes real-time status updates for the satellite team.

    Tracks cumulative character count per round on the ``link`` channel.
    When the simulated time crosses 75% of the round's contact window or
    the window is exceeded, broadcasts a critical or closed notification
    to the channel. A round is considered recovered only if the telemetry
    operator's ``send_command_sequence`` call earns a positive judgment
    from the command judge before the window closes.
    """

    def __init__(
        self,
        cases: list[SatelliteCase],
        team_specs: tuple[TeamSpec, ...],
        postmortem_channel_ids: frozenset[str],
        postmortem_globally_disabled: bool,
    ) -> None:
        super().__init__(
            team_specs=team_specs,
            round_budget_thresholds=(THRESHOLD_WINDOW_CLOSED, THRESHOLD_CRITICAL),
            postmortem_channel_ids=postmortem_channel_ids,
            postmortem_globally_disabled=postmortem_globally_disabled,
        )
        self._cases = cases
        self._current_case: SatelliteCase | None = None
        self._round_recovered: bool = False
        self._round_judge_passed: bool = False
        self._round_window_closed: bool = False
        self._round_outcome_marked: bool = False
        self._round_command_submitted: bool = False
        self._outcome_log: RoundOutcomeLog[SatelliteOutcome] = RoundOutcomeLog(team_ids=(TEAM_ID,))
        self._last_judge_explanation: str = ""
        self._last_violations: tuple[str, ...] = ()
        self._last_submitted_sequence: tuple[CommandStep, ...] = ()

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._world_context

    @property
    def current_case(self) -> SatelliteCase | None:
        """The satellite case for the current round."""
        return self._current_case

    @property
    def current_round_characters(self) -> int:
        """Running character count for the current round on the link channel."""
        return self.characters_used(team_id=TEAM_ID)

    @property
    def round_recovered(self) -> bool:
        """Whether the current round was successfully recovered."""
        return self._round_recovered

    @property
    def round_window_closed(self) -> bool:
        """Whether the current round's contact window has closed."""
        return self._round_window_closed

    @property
    def round_command_submitted(self) -> bool:
        """Whether the operator has already submitted a command sequence this round."""
        return self._round_command_submitted

    @property
    def outcomes(self) -> list[SatelliteOutcome]:
        """Historical per-round outcomes."""
        return self._outcome_log.all_for(team_id=TEAM_ID)

    def previous_outcome(self) -> SatelliteOutcome | None:
        """Return the most recent recorded outcome, or None when no rounds finished."""
        recorded = self._outcome_log.all_for(team_id=TEAM_ID)
        if not recorded:
            return None
        return recorded[-1]

    async def record_command_judgment(
        self,
        judge_passed: bool,
        violations: tuple[str, ...],
        explanation: str,
        submitted_sequence: tuple[CommandStep, ...],
    ) -> None:
        """Update world state after a ``send_command_sequence`` judgment.

        Called from the scenario's tool executor. Sends a terminal status
        notification to the link channel describing whether the round was
        recovered.
        """
        self._round_command_submitted = True
        self._round_judge_passed = judge_passed
        self._last_judge_explanation = explanation
        self._last_violations = violations
        self._last_submitted_sequence = submitted_sequence
        if not judge_passed:
            await self._world_context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=(
                    f"{COMMAND_REJECTED_MARKER}. {SATELLITE_NOT_RECOVERED_MARKER}. "
                    "The submitted command sequence was rejected by review."
                ),
            )
            return
        if self._round_window_closed:
            await self._world_context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=(
                    f"{COMMAND_REJECTED_MARKER}. {SATELLITE_NOT_RECOVERED_MARKER}. "
                    "The submitted sequence was correct but the contact window had "
                    "already closed before submission."
                ),
            )
            return
        self._round_recovered = True
        await self._world_context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
            text=(
                f"{COMMAND_ACCEPTED_MARKER}. {SATELLITE_RECOVERED_MARKER}. "
                "The satellite is back in a safe operating state."
            ),
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
        self._round_window_closed = False
        self._round_outcome_marked = False
        self._round_command_submitted = False
        self._last_judge_explanation = ""
        self._last_violations = ()
        self._last_submitted_sequence = ()

        case_index = (round_number - 1) % len(self._cases)
        self._current_case = self._cases[case_index]

    def _mark_outcome(self, case_number: int) -> None:
        """Append a SatelliteOutcome for the most recently completed round."""
        case = self._current_case
        if case is None:
            return
        self._outcome_log.record(
            team_id=TEAM_ID,
            round_number=case_number,
            outcome=SatelliteOutcome(
                case_number=case_number,
                pattern_name=case.pattern_name,
                recovered=self._round_recovered,
                judge_passed=self._round_judge_passed,
                window_closed=self._round_window_closed,
                characters_used=self.characters_used(team_id=TEAM_ID),
                time_elapsed_seconds=float(self.characters_used(team_id=TEAM_ID)),
                round_time_budget_seconds=case.round_time_budget_seconds,
                pattern_count=len(case.patterns),
                submitted_sequence=self._last_submitted_sequence,
                violations=self._last_violations,
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
        """Accumulate characters and update window state synchronously.

        Called from ``send_message`` before the event is enqueued. Only
        messages on the link channel count toward the contact window;
        postmortem and any other channels are ignored.
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
        if self.characters_used(team_id=TEAM_ID) > self._current_case.round_time_budget_seconds:
            self._round_window_closed = True

    async def on_message_async(self, event: MessageEvent, context: WorldContext) -> None:
        """React to an agent message: push budget/threshold notifications when relevant."""
        if event.channel_id != LINK_CHANNEL_ID:
            return
        await self._send_threshold_notifications(context=context)

    async def _send_threshold_notifications(self, context: WorldContext) -> None:
        """Send status notifications when contact-window thresholds are crossed."""
        if self._current_case is None:
            return
        time_elapsed = self.characters_used(team_id=TEAM_ID)
        budget = self._current_case.round_time_budget_seconds

        if self._round_window_closed and self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=THRESHOLD_WINDOW_CLOSED
        ):
            await context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=(
                    f"{CONTACT_WINDOW_CLOSED_MARKER}. "
                    f"Communication time: {time_elapsed:.0f}s "
                    f"({self.characters_used(team_id=TEAM_ID)} chars) "
                    f"exceeded the contact window of {budget}s."
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
                channel_id=LINK_CHANNEL_ID,
                text=(
                    f"{CONTACT_WINDOW_CRITICAL_MARKER}. "
                    f"{remaining:.0f} seconds of contact remaining."
                ),
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
            team_id=TEAM_ID, round_budget_threshold=THRESHOLD_WINDOW_CLOSED
        ):
            return
        await self._world_context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
            text=f"{SATELLITE_NOT_RECOVERED_MARKER}. {reason}",
        )
