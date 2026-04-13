"""World simulation for the emergency room scenario.

Monitors cumulative radio token usage per round and sends real-time
patient status notifications when time thresholds are crossed. The
patient dies when total communication time exceeds the case's time budget.
A patient is saved only when the field responder calls ``treat_patient`` with
an action that the LLM judge deems adequate.
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
from schmidt.scenarios.emergency_room.patient_cases import PATIENT_CASES, PatientCase

logger = logging.getLogger(__name__)


class PatientOutcome(NamedTuple):
    """Result of a single patient case after a round completes."""

    case_number: int
    condition_name: str
    survived: bool
    tokens_used: int
    time_elapsed_seconds: float
    time_budget_seconds: int


class EmergencyRoomWorld(ScenarioWorld):
    """Monitors radio communication and pushes real-time patient status updates.

    Tracks cumulative word count per round. When the simulated time
    (tokens * seconds_per_token) crosses 50%%, 75%%, or 100%% of the
    patient's time budget, broadcasts a warning, critical, or death
    notification to all agents. A patient survives only if the field responder
    calls ``treat_patient`` with a correct action before time runs out.
    """

    def __init__(self, seconds_per_token: float) -> None:
        self._seconds_per_token = seconds_per_token
        self._current_round_tokens: int = 0
        self._current_case: PatientCase | None = None
        self._patient_alive: bool = True
        self._patient_saved: bool = False
        self._notified_thresholds: set[str] = set()
        self._patient_outcomes: list[PatientOutcome] = []
        self._context: WorldContext | None = None

    @property
    def patient_outcomes(self) -> list[PatientOutcome]:
        """Read-only access to patient outcomes for injection templates."""
        return self._patient_outcomes

    @property
    def patient_alive(self) -> bool:
        """Whether the current patient is still alive."""
        return self._patient_alive

    @property
    def patient_saved(self) -> bool:
        """Whether the current patient has been saved by a correct treatment."""
        return self._patient_saved

    @property
    def current_case(self) -> PatientCase | None:
        """The patient case for the current round."""
        return self._current_case

    def finalize_round_sync(self, round_number: int) -> None:
        """Compute the previous round's outcome and reset state for a new round.

        Called synchronously by the scenario's ``on_round_advanced`` before
        injections are delivered, so outcomes are available for templates.
        Patient survives only if ``save_patient`` was called during the round.
        """
        previous_case_index = round_number - 2
        if 0 <= previous_case_index < len(PATIENT_CASES):
            case = PATIENT_CASES[previous_case_index]
            time_elapsed = self._current_round_tokens * self._seconds_per_token
            self._patient_outcomes.append(
                PatientOutcome(
                    case_number=case.case_number,
                    condition_name=case.condition_name,
                    survived=self._patient_saved,
                    tokens_used=self._current_round_tokens,
                    time_elapsed_seconds=time_elapsed,
                    time_budget_seconds=case.time_budget_seconds,
                )
            )

        self._current_round_tokens = 0
        self._patient_alive = True
        self._patient_saved = False
        self._notified_thresholds = set()

        case_index = round_number - 1
        if case_index < len(PATIENT_CASES):
            self._current_case = PATIENT_CASES[case_index]
        else:
            self._current_case = None

    async def save_patient(self) -> None:
        """Mark the current patient as saved and broadcast to all agents.

        Called by the ``treat_patient`` tool executor when the LLM judge
        confirms the treatment is adequate.
        """
        self._patient_saved = True
        if self._context is not None:
            await self._context.send_update(
                text="PATIENT SAVED. Treatment successful.",
            )

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate tokens and update patient alive state synchronously.

        Called from ``send_message`` before the event is enqueued, so
        ``treat_patient`` sees correct state immediately.
        """
        _ = agent_id, channel_id, text
        self._current_round_tokens += token_count

        if self._current_case is None:
            return
        if not self._patient_alive:
            return
        if self._patient_saved:
            return

        time_elapsed = self._current_round_tokens * self._seconds_per_token
        budget = self._current_case.time_budget_seconds
        if time_elapsed > budget:
            self._patient_alive = False

    async def run(self, context: WorldContext) -> None:
        """Process events and send async notifications for threshold crossings."""
        self._context = context
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    pass
                elif isinstance(event, MessageEvent):
                    await self._send_threshold_notifications(context=context)
        except asyncio.CancelledError:
            return

    async def _send_threshold_notifications(self, context: WorldContext) -> None:
        """Send patient status notifications for any newly crossed thresholds."""
        if self._current_case is None:
            return

        time_elapsed = self._current_round_tokens * self._seconds_per_token
        budget = self._current_case.time_budget_seconds

        if not self._patient_alive and "dead" not in self._notified_thresholds:
            self._notified_thresholds.add("dead")
            await context.send_update(
                text=(
                    f"PATIENT HAS DIED. "
                    f"Radio time: {time_elapsed:.0f}s exceeded budget of {budget}s."
                ),
            )
        elif self._patient_saved:
            return
        elif time_elapsed > budget * 0.75 and "critical" not in self._notified_thresholds:
            self._notified_thresholds.add("critical")
            remaining = budget - time_elapsed
            await context.send_update(
                text=(
                    f"CRITICAL: Patient deteriorating rapidly. "
                    f"{remaining:.0f} seconds remaining."
                ),
            )
        elif time_elapsed > budget * 0.5 and "warning" not in self._notified_thresholds:
            self._notified_thresholds.add("warning")
            remaining = budget - time_elapsed
            await context.send_update(
                text=(
                    f"WARNING: Patient condition worsening. " f"{remaining:.0f} seconds remaining."
                ),
            )
