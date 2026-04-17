"""World simulation for the Veyru stabilization scenario.

Monitors cumulative communication character usage per round and sends
real-time Veyru status notifications when time thresholds are crossed.
The Veyru collapses when total communication time exceeds the case's time
budget. A Veyru is stabilized only when the field observer calls
``stabilize_veyru`` with an action that the LLM judge deems adequate.
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
from schmidt.scenarios.veyru.veyru_cases import VeyruCase, VeyruStage

logger = logging.getLogger(__name__)

POSTMORTEM_CHANNEL_ID = "postmortem"


class StageOutcome(NamedTuple):
    """Result of a single stage within a composite case."""

    motif_name: str
    stabilized: bool


class VeyruOutcome(NamedTuple):
    """Result of a single Veyru case after a round completes."""

    case_number: int
    failure_name: str
    stabilized: bool
    characters_used: int
    time_elapsed_seconds: float
    time_budget_seconds: int
    stages_completed: int
    total_stages: int
    stage_outcomes: tuple[StageOutcome, ...]


class VeyruWorld(ScenarioWorld):
    """Monitors communication and pushes real-time Veyru status updates.

    Tracks cumulative character count per round. When the simulated time
    (characters * seconds_per_character) crosses 50%%, 75%%, or 100%% of the
    Veyru's time budget, broadcasts a warning, critical, or collapse
    notification to all agents. A Veyru survives only if the field observer
    calls ``stabilize_veyru`` with a correct action before time runs out.
    """

    def __init__(
        self,
        seconds_per_character: float,
        veyru_cases: list[VeyruCase],
    ) -> None:
        self._seconds_per_character = seconds_per_character
        self._veyru_cases = veyru_cases
        self._current_round_characters: int = 0
        self._current_case: VeyruCase | None = None
        self._veyru_alive: bool = True
        self._veyru_stabilized: bool = False
        self._notified_thresholds: set[str] = set()
        self._veyru_outcomes: list[VeyruOutcome] = []
        self._context: WorldContext | None = None
        self._in_postmortem: bool = False
        self._current_stage_index: int = 0
        self._stage_outcomes: list[StageOutcome] = []

    @property
    def veyru_outcomes(self) -> list[VeyruOutcome]:
        """Read-only access to Veyru outcomes for injection templates."""
        return self._veyru_outcomes

    @property
    def veyru_alive(self) -> bool:
        """Whether the current Veyru is still stable enough to be saved."""
        return self._veyru_alive

    @property
    def veyru_stabilized(self) -> bool:
        """Whether the current Veyru has been stabilized by a correct action."""
        return self._veyru_stabilized

    @property
    def current_case(self) -> VeyruCase | None:
        """The Veyru case for the current round."""
        return self._current_case

    @property
    def current_stage(self) -> VeyruStage | None:
        """The currently active stage, or None if no case is loaded."""
        if self._current_case is None:
            return None
        if self._current_stage_index >= len(self._current_case.stages):
            return None
        return self._current_case.stages[self._current_stage_index]

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is in a postmortem discussion phase."""
        return self._in_postmortem

    def enter_postmortem(self) -> None:
        """Mark the start of a postmortem discussion phase."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Mark the end of a postmortem discussion phase."""
        self._in_postmortem = False

    def compute_outcome_if_needed(self, round_number: int) -> VeyruOutcome | None:
        """Compute and store the outcome for the given round if not already done.

        Returns the outcome, or None if no outcome can be computed (round 0).
        Used by postmortem injections to access results before the next round
        resets state.
        """
        if round_number < 1:
            return None

        for existing in self._veyru_outcomes:
            if existing.case_number == round_number:
                return existing

        case_index = (round_number - 1) % len(self._veyru_cases)
        case = self._veyru_cases[case_index]
        time_elapsed = self._current_round_characters * self._seconds_per_character

        all_stage_outcomes = list(self._stage_outcomes)
        for i in range(len(all_stage_outcomes), len(case.stages)):
            all_stage_outcomes.append(
                StageOutcome(
                    motif_name=case.stages[i].motif_name,
                    stabilized=False,
                )
            )

        outcome = VeyruOutcome(
            case_number=round_number,
            failure_name=case.failure_name,
            stabilized=self._veyru_stabilized,
            characters_used=self._current_round_characters,
            time_elapsed_seconds=time_elapsed,
            time_budget_seconds=case.time_budget_seconds,
            stages_completed=len(self._stage_outcomes),
            total_stages=len(case.stages),
            stage_outcomes=tuple(all_stage_outcomes),
        )
        self._veyru_outcomes.append(outcome)
        return outcome

    def finalize_round_sync(self, round_number: int) -> None:
        """Compute the previous round's outcome and reset state for a new round.

        Called synchronously by the scenario's ``on_round_advanced`` before
        injections are delivered, so outcomes are available for templates.
        Veyru survives only if ``stabilize_veyru`` was called during the round.
        """
        if round_number >= 2:
            self.compute_outcome_if_needed(round_number=round_number - 1)

        self._current_round_characters = 0
        self._veyru_alive = True
        self._veyru_stabilized = False
        self._notified_thresholds = set()
        self._current_stage_index = 0
        self._stage_outcomes = []

        case_index = (round_number - 1) % len(self._veyru_cases)
        self._current_case = self._veyru_cases[case_index]

    async def stabilize_veyru(self) -> bool:
        """Advance to the next stage or fully stabilize the current Veyru.

        Records the current stage as stabilized. If more stages remain,
        advances the stage index and broadcasts a generic notification
        (symptoms go to the observer via the tool result, not here).
        If all stages are done, marks the Veyru as fully stabilized.

        Returns True if more stages remain, False if fully stabilized.
        """
        if self._current_case is None:
            return False

        stage = self._current_case.stages[self._current_stage_index]
        self._stage_outcomes.append(StageOutcome(motif_name=stage.motif_name, stabilized=True))

        next_index = self._current_stage_index + 1
        if next_index >= len(self._current_case.stages):
            self._veyru_stabilized = True
            if self._context is not None:
                await self._context.send_update(
                    text="VEYRU STABILIZED. All issues resolved.",
                )
            return False

        self._current_stage_index = next_index
        if self._context is not None:
            await self._context.send_update(
                text="Issue stabilized, but the Veyru remains unstable — new symptoms detected.",
            )
        return True

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate characters and update Veyru alive state synchronously.

        Called from ``send_message`` before the event is enqueued, so
        ``stabilize_veyru`` sees correct state immediately. Postmortem
        channel messages do not count toward the budget.
        """
        _ = agent_id, token_count
        if channel_id == POSTMORTEM_CHANNEL_ID:
            return

        self._current_round_characters += len(text)

        if self._current_case is None:
            return
        if not self._veyru_alive:
            return
        if self._veyru_stabilized:
            return

        time_elapsed = self._current_round_characters * self._seconds_per_character
        budget = self._current_case.time_budget_seconds
        if time_elapsed > budget:
            self._veyru_alive = False

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
        """Send Veyru status notifications when critical thresholds are crossed.

        Only two notification levels: CRITICAL at 75% budget used, and
        COLLAPSED at 100%. A single CRITICAL notification per round avoids
        noisy bursts where multiple threshold alerts arrive in the same
        agent notification batch.
        """
        if self._current_case is None:
            return

        time_elapsed = self._current_round_characters * self._seconds_per_character
        budget = self._current_case.time_budget_seconds

        if not self._veyru_alive and "collapsed" not in self._notified_thresholds:
            self._notified_thresholds.update(["collapsed", "critical"])
            await context.send_update(
                text=(
                    f"VEYRU HAS COLLAPSED. "
                    f"Communication time: {time_elapsed:.0f}s "
                    f"({self._current_round_characters} chars) "
                    f"exceeded budget of {budget}s."
                ),
            )
        elif self._veyru_stabilized:
            return
        elif time_elapsed > budget * 0.75 and "critical" not in self._notified_thresholds:
            self._notified_thresholds.add("critical")
            remaining = budget - time_elapsed
            await context.send_update(
                text=(f"CRITICAL: Veyru destabilizing rapidly. {remaining:.0f} seconds remaining."),
            )
