"""World simulation for the spillway_release scenario.

Tracks the running character count on the ops channel and the three agents'
committed actions for the current round: the dam operator's gate setting,
whether the park ranger secured the park, and whether civil defense ordered
an evacuation. The tools mutate this state synchronously; at round end the
scenario calls :meth:`mark_round_outcome`, which applies the deterministic
:func:`resolve_round` rule and appends a ``SpillwayOutcome``.

The world is single-team: one shared ops channel with all three agents.
Every character sent on it costs one simulated second against the round's
budget, and the round fails when the running total reaches the budget.
"""

import asyncio
import logging

from glossogen.runtime.scenario_world import RoundAdvancedEvent, ScenarioWorld, WorldContext
from glossogen.scenarios.spillway_release.ids import (
    BUDGET_EXCEEDED_MARKER,
    OPS_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    ROUND_FAILED_MARKER,
    ROUND_SUCCESS_MARKER,
)
from glossogen.scenarios.spillway_release.spillway_cases import SpillwayCase
from glossogen.scenarios.spillway_release.world_state import SpillwayOutcome, resolve_round

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"


__all__ = [
    "SpillwayOutcome",
    "SpillwayWorld",
]


class SpillwayWorld(ScenarioWorld):
    """Single-team reservoir world that resolves each round deterministically."""

    _context: WorldContext

    def __init__(
        self,
        cases: list[SpillwayCase],
        postmortem_globally_disabled: bool,
    ) -> None:
        self._cases = cases
        self._current_case: SpillwayCase | None = None
        self._in_postmortem: bool = False
        self._postmortem_globally_disabled: bool = postmortem_globally_disabled
        self._current_round_characters: int = 0
        self._round_budget_exceeded: bool = False
        self._gates_opened: int = 0
        self._release_duration_hours: float = 0.0
        self._park_secured: bool = False
        self._evacuated: bool = False
        self._notified_thresholds: set[str] = set()
        self._round_outcome_marked: bool = False
        self._outcomes: list[SpillwayOutcome] = []

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def current_case(self) -> SpillwayCase | None:
        """The spillway case for the current round."""
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
        """Running character count on the ops channel this round."""
        return self._current_round_characters

    @property
    def round_budget_exceeded(self) -> bool:
        """Whether the communication budget has been exceeded this round."""
        return self._round_budget_exceeded

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
        """Postmortem channel when globally disabled, else empty."""
        if not self._postmortem_globally_disabled:
            return frozenset()
        return frozenset({POSTMORTEM_CHANNEL_ID})

    def commit_gates(self, gate_count_opened: int, duration_hours: float) -> None:
        """Record the dam operator's gate setting for this round (last call wins)."""
        self._gates_opened = gate_count_opened
        self._release_duration_hours = duration_hours

    def secure_park(self) -> None:
        """Record that the park ranger secured the park (closed / kept closed)."""
        self._park_secured = True

    def order_evacuation(self) -> None:
        """Record that civil defense ordered a downstream evacuation."""
        self._evacuated = True

    @property
    def park_secured(self) -> bool:
        """Whether the park has been secured this round."""
        return self._park_secured

    @property
    def evacuated(self) -> bool:
        """Whether civil defense has evacuated downstream this round."""
        return self._evacuated

    def previous_outcome(self) -> SpillwayOutcome | None:
        """Return the most recent finished round's outcome, or None on round 1."""
        if len(self._outcomes) == 0:
            return None
        return self._outcomes[-1]

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate ops-channel characters and flag budget exhaustion synchronously."""
        _ = agent_id, token_count
        if channel_id != OPS_CHANNEL_ID:
            return
        self._current_round_characters += len(text)
        if self._current_case is None:
            return
        if self._current_round_characters >= self._current_case.round_time_budget_seconds:
            self._round_budget_exceeded = True

    def finalize_round_sync(self, round_number: int) -> None:
        """Mark the previous round's outcome, reset per-round state, load the next case."""
        assert (
            1 <= round_number <= len(self._cases)
        ), f"round_number {round_number} out of range [1, {len(self._cases)}]"
        if round_number >= 2 and not self._round_outcome_marked:
            self._mark_outcome()
        self._current_case = self._cases[round_number - 1]
        self._current_round_characters = 0
        self._round_budget_exceeded = False
        self._gates_opened = 0
        self._release_duration_hours = 0.0
        self._park_secured = False
        self._evacuated = False
        self._notified_thresholds = set()
        self._round_outcome_marked = False

    def mark_round_outcome(self, round_number: int) -> None:
        """Resolve and append the current round's outcome if not already marked."""
        _ = round_number
        if self._round_outcome_marked:
            return
        self._mark_outcome()

    def _mark_outcome(self) -> None:
        """Resolve the current round and append its outcome.

        Resolves against ``_current_case``, whose ``case_number`` is the round
        being marked (the previous round during ``finalize_round_sync``, the
        current round during ``mark_round_outcome``).
        """
        case = self._current_case
        if case is None:
            return
        outcome = resolve_round(
            case=case,
            gates_opened=self._gates_opened,
            release_duration_hours=self._release_duration_hours,
            park_secured=self._park_secured,
            evacuated=self._evacuated,
            characters_used=self._current_round_characters,
            budget_exceeded=self._round_budget_exceeded,
        )
        self._outcomes.append(outcome)
        self._round_outcome_marked = True

    def current_outcome(self) -> SpillwayOutcome | None:
        """Resolve the current round's state without recording it (for round-end events)."""
        case = self._current_case
        if case is None:
            return None
        return resolve_round(
            case=case,
            gates_opened=self._gates_opened,
            release_duration_hours=self._release_duration_hours,
            park_secured=self._park_secured,
            evacuated=self._evacuated,
            characters_used=self._current_round_characters,
            budget_exceeded=self._round_budget_exceeded,
        )

    async def run(self, context: WorldContext) -> None:
        """Process events and push budget-threshold notifications to the ops channel."""
        self._context = context
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    continue
                if event.channel_id != OPS_CHANNEL_ID:
                    continue
                await self._send_threshold_notifications(context=context)
        except asyncio.CancelledError:
            return

    async def _send_threshold_notifications(self, context: WorldContext) -> None:
        """Notify the ops channel when the communication budget crosses 75% / 100%."""
        case = self._current_case
        if case is None:
            return
        elapsed = self._current_round_characters
        budget = case.round_time_budget_seconds
        if (
            self._round_budget_exceeded
            and THRESHOLD_BUDGET_EXCEEDED not in self._notified_thresholds
        ):
            self._notified_thresholds.update([THRESHOLD_BUDGET_EXCEEDED, THRESHOLD_CRITICAL])
            await context.send_update_to_channel(
                channel_id=OPS_CHANNEL_ID,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. Communication time: {elapsed} chars exceeded "
                    f"the {budget}s coordination window."
                ),
            )
            return
        if elapsed >= budget * 0.75 and THRESHOLD_CRITICAL not in self._notified_thresholds:
            self._notified_thresholds.add(THRESHOLD_CRITICAL)
            remaining = budget - elapsed
            await context.send_update_to_channel(
                channel_id=OPS_CHANNEL_ID,
                text=f"CRITICAL: coordination window almost spent. {remaining} seconds remaining.",
            )

    async def emit_round_terminal_notification(self) -> None:
        """Emit the round's success / failure marker to the ops channel."""
        outcome = self.current_outcome()
        if outcome is None:
            return
        if outcome.round_succeeded:
            text = (
                f"{ROUND_SUCCESS_MARKER}. Reservoir ended at {outcome.end_level:.0f}% "
                "and no one downstream was harmed."
            )
        else:
            text = f"{ROUND_FAILED_MARKER}. {outcome.failure_reason}"
        await self._context.send_update_to_channel(channel_id=OPS_CHANNEL_ID, text=text)
