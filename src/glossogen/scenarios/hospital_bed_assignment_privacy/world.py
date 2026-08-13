"""World simulation for the hospital bed-assignment privacy scenario.

Tracks the per-round bed-board case, the running communication budget on the
public ops channel, the Transport Lead's routing submission (overwrite-wins),
the Unauthorized Observer's intercept submissions (any (token, destination)
pair match counts as a successful intercept), restricted-vocabulary leakage
by the Bed Manager, and the resolved per-round outcomes. Outcomes are
finalized in ``finalize_round_sync`` at round advance.
"""

import logging
from typing import NamedTuple

from glossogen.engine.round_outcome_log import RoundOutcomeLog
from glossogen.engine.round_world import RoundWorld
from glossogen.engine.team_declaration import TeamSpec
from glossogen.runtime.scenario_world import MessageEvent, WorldContext
from glossogen.scenarios.hospital_bed_assignment_privacy.hospital_cases import HospitalCase
from glossogen.scenarios.hospital_bed_assignment_privacy.ids import (
    BED_MANAGER_ID,
    BUDGET_EXCEEDED_MARKER,
    PUBLIC_OPS_CHANNEL_ID,
    ROUND_FAILED_MARKER,
    ROUND_SUCCESS_MARKER,
)
from glossogen.scenarios.hospital_bed_assignment_privacy.team_declaration import TEAM_ID

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"


class HospitalRouting(NamedTuple):
    """The Transport Lead's most recent ``route_patient`` submission this round."""

    submitted_patient_token: str
    submitted_destination: str
    submitted_transport_mode: str
    patient_token_correct: bool
    destination_correct: bool
    transport_mode_correct: bool


class HospitalIntercept(NamedTuple):
    """One ``submit_intercept`` attempt by the Unauthorized Observer this round."""

    submitted_patient_token: str
    submitted_destination: str
    patient_token_match: bool
    destination_match: bool
    pair_match: bool


class HospitalOutcome(NamedTuple):
    """Result of a single round after both sides have submitted.

    ``full_success`` is the only outcome that rewards the team: the
    Transport Lead routed every field correctly, the Observer never
    matched the hidden (patient_token, destination) pair, and the
    communication budget was not exhausted. ``privacy_violated`` is
    tracked but does not affect ``full_success``.
    """

    round_number: int
    case_number: int
    transport_correct: bool
    observer_intercepted: bool
    budget_exceeded: bool
    privacy_violated: bool
    privacy_violations: tuple[str, ...]
    characters_used: int
    time_budget_seconds: int | None
    routing: HospitalRouting | None
    intercepts: tuple[HospitalIntercept, ...]
    full_success: bool


class HospitalWorld(RoundWorld):
    """Live state for the hospital bed-assignment privacy scenario.

    The world tracks per-round message budget, the Transport Lead's
    routing submission, the Observer's intercept submissions, and the
    Bed Manager's restricted-vocabulary leakage on the public channel.
    Outcomes are resolved in ``finalize_round_sync`` at the start of the
    next round.
    """

    def __init__(
        self,
        cases: list[HospitalCase],
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
        self._current_case: HospitalCase | None = None
        self._current_round_number: int = 0
        self._round_budget_exceeded: bool = False
        self._pending_routing: HospitalRouting | None = None
        self._pending_intercepts: list[HospitalIntercept] = []
        self._privacy_violations: list[str] = []
        self._outcome_log: RoundOutcomeLog[HospitalOutcome] = RoundOutcomeLog(team_ids=(TEAM_ID,))

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._world_context

    @property
    def current_case(self) -> HospitalCase | None:
        """The bed-board case for the round currently in play."""
        return self._current_case

    @property
    def round_budget_exceeded(self) -> bool:
        """Whether the current round has exceeded its communication budget."""
        return self._round_budget_exceeded

    @property
    def outcomes(self) -> list[HospitalOutcome]:
        """All resolved round outcomes in order."""
        return self._outcome_log.all_for(team_id=TEAM_ID)

    def previous_outcome(self) -> HospitalOutcome | None:
        """Return the most recent recorded outcome, or None when no rounds have ended."""
        recorded = self._outcome_log.all_for(team_id=TEAM_ID)
        if not recorded:
            return None
        return recorded[-1]

    def record_routing(self, routing: HospitalRouting) -> None:
        """Store the Transport Lead's latest routing submission (overwrite-wins)."""
        self._pending_routing = routing

    def record_intercept(self, intercept: HospitalIntercept) -> None:
        """Append one Observer intercept submission to the pending list."""
        self._pending_intercepts.append(intercept)

    def intercept_submission_count(self) -> int:
        """Return how many intercept guesses the Observer has made this round."""
        return len(self._pending_intercepts)

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate public-channel characters and scan for restricted-vocab leaks.

        Called from ``send_message`` before the event is enqueued. Only
        messages on the public ops channel count toward the budget; the
        postmortem channel is ignored. Restricted-vocabulary scanning is
        case-insensitive substring matching against Bed Manager messages.
        """
        super().on_message(
            agent_id=agent_id, channel_id=channel_id, text=text, token_count=token_count
        )
        if not self.meters_channel(channel_id=channel_id):
            return
        case = self._current_case
        if case is None:
            return
        budget = case.round_time_budget_seconds
        if (
            budget is not None
            and self.characters_used(team_id=TEAM_ID) > budget
            and not self._round_budget_exceeded
        ):
            self._round_budget_exceeded = True
        if agent_id == BED_MANAGER_ID:
            lowered_text = text.lower()
            for word in case.restricted_vocabulary:
                if word.lower() in lowered_text:
                    self._privacy_violations.append(word)

    async def on_message_async(self, event: MessageEvent, context: WorldContext) -> None:
        """React to an agent message: push budget/threshold notifications when relevant."""
        if event.channel_id != PUBLIC_OPS_CHANNEL_ID:
            return
        await self._send_threshold_notifications(context=context)

    async def _send_threshold_notifications(self, context: WorldContext) -> None:
        """Send status notifications when budget thresholds are first crossed."""
        case = self._current_case
        if case is None:
            return
        budget = case.round_time_budget_seconds
        if budget is None:
            return
        time_elapsed = self.characters_used(team_id=TEAM_ID)

        if self._round_budget_exceeded and self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=THRESHOLD_BUDGET_EXCEEDED
        ):
            await context.send_update_to_channel(
                channel_id=PUBLIC_OPS_CHANNEL_ID,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. "
                    f"Communication time: {time_elapsed}s "
                    f"({time_elapsed} chars) exceeded budget of {budget}s."
                ),
            )
            return
        if time_elapsed > budget * 0.75 and self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=THRESHOLD_CRITICAL
        ):
            remaining = budget - time_elapsed
            await context.send_update_to_channel(
                channel_id=PUBLIC_OPS_CHANNEL_ID,
                text=(f"CRITICAL: Communication budget narrowing. {remaining}s remaining."),
            )

    def compute_outcome_if_needed(self, round_number: int) -> HospitalOutcome | None:
        """Resolve and cache the outcome for ``round_number`` if not already done.

        Returns the cached outcome on subsequent calls. If ``round_number``
        does not match the current round and no cached outcome exists,
        returns None. The pending guess state is only meaningful for the
        round currently in play.
        """
        if round_number < 1:
            return None
        recorded = self._outcome_log.recorded_for(team_id=TEAM_ID, round_number=round_number)
        if recorded is not None:
            return recorded
        if round_number != self._current_round_number:
            return None
        case = self._current_case
        if case is None:
            return None
        routing = self._pending_routing
        transport_correct = (
            routing is not None
            and routing.patient_token_correct
            and routing.destination_correct
            and routing.transport_mode_correct
        )
        observer_intercepted = any(intercept.pair_match for intercept in self._pending_intercepts)
        privacy_violations = tuple(self._privacy_violations)
        privacy_violated = len(privacy_violations) > 0
        full_success = (
            transport_correct and not observer_intercepted and not self._round_budget_exceeded
        )
        outcome = HospitalOutcome(
            round_number=round_number,
            case_number=case.case_number,
            transport_correct=transport_correct,
            observer_intercepted=observer_intercepted,
            budget_exceeded=self._round_budget_exceeded,
            privacy_violated=privacy_violated,
            privacy_violations=privacy_violations,
            characters_used=self.characters_used(team_id=TEAM_ID),
            time_budget_seconds=case.round_time_budget_seconds,
            routing=routing,
            intercepts=tuple(self._pending_intercepts),
            full_success=full_success,
        )
        return self._outcome_log.record(team_id=TEAM_ID, round_number=round_number, outcome=outcome)

    def finalize_round_sync(self, new_round_number: int) -> None:
        """Resolve the previous round (if any) and advance to ``new_round_number``.

        Called by the scenario's ``on_round_advanced`` hook before the
        next round's injections are rendered. Idempotent for the same
        round via ``compute_outcome_if_needed``.
        """
        if new_round_number >= 2:
            self.compute_outcome_if_needed(round_number=new_round_number - 1)

        self._current_round_number = new_round_number
        # After the outcome above, which reads the round that just ended.
        self.begin_round()
        self._round_budget_exceeded = False
        self._pending_routing = None
        self._pending_intercepts = []
        self._privacy_violations = []

        case_index = (new_round_number - 1) % len(self._cases)
        self._current_case = self._cases[case_index]

    def append_restored_outcome(self, outcome: HospitalOutcome) -> None:
        """Append a pre-built outcome (used by ``restore_state_from_events``)."""
        self._outcome_log.record(
            team_id=TEAM_ID, round_number=outcome.round_number, outcome=outcome
        )

    def has_pending_routing(self) -> bool:
        """Return True if the Transport Lead has already routed this round."""
        return self._pending_routing is not None

    async def emit_round_terminal_notification(self, outcome: HospitalOutcome) -> None:
        """Push the round-success or round-failed marker to the public ops channel."""
        if outcome.full_success:
            text = (
                f"{ROUND_SUCCESS_MARKER}. Patient routed correctly; "
                "no intercept matched; budget intact."
            )
        else:
            reasons: list[str] = []
            if not outcome.transport_correct:
                reasons.append("routing incorrect")
            if outcome.observer_intercepted:
                reasons.append("intercept matched")
            if outcome.budget_exceeded:
                reasons.append("budget exceeded")
            if len(reasons) == 0:
                reasons.append("round ended without success")
            text = f"{ROUND_FAILED_MARKER}. {'; '.join(reasons)}."
        await self._world_context.send_update_to_channel(
            channel_id=PUBLIC_OPS_CHANNEL_ID,
            text=text,
        )
