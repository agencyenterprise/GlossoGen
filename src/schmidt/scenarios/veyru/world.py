"""World simulation for the Veyru stabilization scenario.

Monitors cumulative communication token usage per round and sends real-time
Veyru status notifications when time thresholds are crossed. The Veyru
collapses when total communication time exceeds the case's time budget.
A Veyru is stabilized only when the field observer calls ``stabilize_veyru``
with an action that the LLM judge deems adequate.
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
from schmidt.scenarios.veyru.veyru_cases import VEYRU_CASES, VeyruCase

logger = logging.getLogger(__name__)


class VeyruOutcome(NamedTuple):
    """Result of a single Veyru case after a round completes."""

    case_number: int
    failure_name: str
    stabilized: bool
    tokens_used: int
    time_elapsed_seconds: float
    time_budget_seconds: int


class VeyruWorld(ScenarioWorld):
    """Monitors communication and pushes real-time Veyru status updates.

    Tracks cumulative word count per round. When the simulated time
    (tokens * seconds_per_token) crosses 50%%, 75%%, or 100%% of the
    Veyru's time budget, broadcasts a warning, critical, or collapse
    notification to all agents. A Veyru survives only if the field observer
    calls ``stabilize_veyru`` with a correct action before time runs out.
    """

    def __init__(self, seconds_per_token: float) -> None:
        self._seconds_per_token = seconds_per_token
        self._current_round_tokens: int = 0
        self._current_case: VeyruCase | None = None
        self._veyru_alive: bool = True
        self._veyru_stabilized: bool = False
        self._notified_thresholds: set[str] = set()
        self._veyru_outcomes: list[VeyruOutcome] = []
        self._context: WorldContext | None = None

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

    def finalize_round_sync(self, round_number: int) -> None:
        """Compute the previous round's outcome and reset state for a new round.

        Called synchronously by the scenario's ``on_round_advanced`` before
        injections are delivered, so outcomes are available for templates.
        Veyru survives only if ``stabilize_veyru`` was called during the round.
        """
        previous_case_index = round_number - 2
        if 0 <= previous_case_index < len(VEYRU_CASES):
            case = VEYRU_CASES[previous_case_index]
            time_elapsed = self._current_round_tokens * self._seconds_per_token
            self._veyru_outcomes.append(
                VeyruOutcome(
                    case_number=case.case_number,
                    failure_name=case.failure_name,
                    stabilized=self._veyru_stabilized,
                    tokens_used=self._current_round_tokens,
                    time_elapsed_seconds=time_elapsed,
                    time_budget_seconds=case.time_budget_seconds,
                )
            )

        self._current_round_tokens = 0
        self._veyru_alive = True
        self._veyru_stabilized = False
        self._notified_thresholds = set()

        case_index = round_number - 1
        if case_index < len(VEYRU_CASES):
            self._current_case = VEYRU_CASES[case_index]
        else:
            self._current_case = None

    async def stabilize_veyru(self) -> None:
        """Mark the current Veyru as stabilized and broadcast to all agents.

        Called by the ``stabilize_veyru`` tool executor when the LLM judge
        confirms the stabilization action is adequate.
        """
        self._veyru_stabilized = True
        if self._context is not None:
            await self._context.send_update(
                text="VEYRU STABILIZED. Action successful.",
            )

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate tokens and update Veyru alive state synchronously.

        Called from ``send_message`` before the event is enqueued, so
        ``stabilize_veyru`` sees correct state immediately.
        """
        _ = agent_id, channel_id, text
        self._current_round_tokens += token_count

        if self._current_case is None:
            return
        if not self._veyru_alive:
            return
        if self._veyru_stabilized:
            return

        time_elapsed = self._current_round_tokens * self._seconds_per_token
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
        """Send Veyru status notifications for any newly crossed thresholds."""
        if self._current_case is None:
            return

        time_elapsed = self._current_round_tokens * self._seconds_per_token
        budget = self._current_case.time_budget_seconds

        if not self._veyru_alive and "collapsed" not in self._notified_thresholds:
            self._notified_thresholds.add("collapsed")
            await context.send_update(
                text=(
                    f"VEYRU HAS COLLAPSED. "
                    f"Comm time: {time_elapsed:.0f}s exceeded budget of {budget}s."
                ),
            )
        elif self._veyru_stabilized:
            return
        elif time_elapsed > budget * 0.75 and "critical" not in self._notified_thresholds:
            self._notified_thresholds.add("critical")
            remaining = budget - time_elapsed
            await context.send_update(
                text=(
                    f"CRITICAL: Veyru destabilizing rapidly. " f"{remaining:.0f} seconds remaining."
                ),
            )
        elif time_elapsed > budget * 0.5 and "warning" not in self._notified_thresholds:
            self._notified_thresholds.add("warning")
            remaining = budget - time_elapsed
            await context.send_update(
                text=(
                    f"WARNING: Veyru condition worsening. " f"{remaining:.0f} seconds remaining."
                ),
            )
