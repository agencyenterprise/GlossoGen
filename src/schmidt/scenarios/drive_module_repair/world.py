"""World simulation for the drive_module_repair scenario.

Tracks the running character count on the bay channel and the technician's
progress through the round's ordered replacement stages. Each accepted
``replace_component`` advances the stage index (the order is hard-enforced:
only the current required replacement is accepted); completing every stage
repairs the device. The round fails if the communication budget is exhausted
or the round ends before every component is correctly replaced.

The world is single-team: one shared bay channel with all three agents.
Every character sent on it costs one simulated second against the round's
budget.
"""

import asyncio
import logging

from schmidt.runtime.scenario_world import RoundAdvancedEvent, ScenarioWorld, WorldContext
from schmidt.scenarios.drive_module_repair.drive_module_cases import DriveModuleCase, Stage
from schmidt.scenarios.drive_module_repair.ids import (
    BAY_CHANNEL_ID,
    BUDGET_EXCEEDED_MARKER,
    DEVICE_FAILED_MARKER,
    DEVICE_REPAIRED_MARKER,
    POSTMORTEM_CHANNEL_ID,
)
from schmidt.scenarios.drive_module_repair.world_state import DriveModuleOutcome

logger = logging.getLogger(__name__)

THRESHOLD_BUDGET_EXCEEDED = "budget_exceeded"
THRESHOLD_CRITICAL = "critical"


__all__ = [
    "DriveModuleOutcome",
    "DriveModuleWorld",
]


class DriveModuleWorld(ScenarioWorld):
    """Single-team world that advances through ordered replacement stages."""

    _context: WorldContext

    def __init__(
        self,
        cases: list[DriveModuleCase],
        postmortem_globally_disabled: bool,
    ) -> None:
        self._cases = cases
        self._current_case: DriveModuleCase | None = None
        self._in_postmortem: bool = False
        self._postmortem_globally_disabled: bool = postmortem_globally_disabled
        self._current_round_characters: int = 0
        self._round_budget_exceeded: bool = False
        self._current_stage_index: int = 0
        self._notified_thresholds: set[str] = set()
        self._round_outcome_marked: bool = False
        self._outcomes: list[DriveModuleOutcome] = []

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def current_case(self) -> DriveModuleCase | None:
        """The drive-module case for the current round."""
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

    def get_current_stage(self) -> Stage | None:
        """Return the replacement the technician must perform next, or None."""
        case = self._current_case
        if case is None:
            return None
        if self._current_stage_index >= len(case.stages):
            return None
        return case.stages[self._current_stage_index]

    def is_device_repaired(self) -> bool:
        """Whether every required replacement has been correctly performed."""
        case = self._current_case
        if case is None:
            return False
        return self._current_stage_index >= len(case.stages)

    async def perform_replacement(self) -> bool:
        """Accept the current replacement and advance the stage index.

        Returns True if more replacements remain, False if the device is now
        fully repaired. Broadcasts a generic progress notification to the bay
        channel (the next component's identity stays with the engineers).
        """
        case = self._current_case
        if case is None:
            return False
        self._current_stage_index += 1
        if self._current_stage_index >= len(case.stages):
            await self._context.send_update_to_channel(
                channel_id=BAY_CHANNEL_ID,
                text=f"{DEVICE_REPAIRED_MARKER}. All components replaced.",
            )
            return False
        await self._context.send_update_to_channel(
            channel_id=BAY_CHANNEL_ID,
            text="Replacement accepted; the module still needs more work.",
        )
        return True

    def previous_outcome(self) -> DriveModuleOutcome | None:
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
        """Accumulate bay-channel characters and flag budget exhaustion synchronously."""
        _ = agent_id, token_count
        if channel_id != BAY_CHANNEL_ID:
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
        self._current_stage_index = 0
        self._notified_thresholds = set()
        self._round_outcome_marked = False

    def mark_round_outcome(self, round_number: int) -> None:
        """Resolve and append the current round's outcome if not already marked."""
        _ = round_number
        if self._round_outcome_marked:
            return
        self._mark_outcome()

    def _resolve(self) -> DriveModuleOutcome:
        """Compute the current round's outcome from live state."""
        case = self._current_case
        assert case is not None, "cannot resolve before a case is loaded"
        device_repaired = self._current_stage_index >= len(case.stages)
        round_succeeded = device_repaired and not self._round_budget_exceeded
        if self._round_budget_exceeded:
            failure_reason = "Communication budget exhausted."
        elif not device_repaired:
            failure_reason = "Round ended before all components were correctly replaced."
        else:
            failure_reason = ""
        return DriveModuleOutcome(
            case_number=case.case_number,
            replacement_count=case.replacement_count,
            replacements_done=min(self._current_stage_index, len(case.stages)),
            budget_exceeded=self._round_budget_exceeded,
            characters_used=self._current_round_characters,
            round_time_budget_seconds=case.round_time_budget_seconds,
            device_repaired=device_repaired,
            round_succeeded=round_succeeded,
            failure_reason=failure_reason,
        )

    def _mark_outcome(self) -> None:
        """Resolve the current round and append its outcome."""
        if self._current_case is None:
            return
        self._outcomes.append(self._resolve())
        self._round_outcome_marked = True

    def current_outcome(self) -> DriveModuleOutcome | None:
        """Resolve the current round's state without recording it (for round-end events)."""
        if self._current_case is None:
            return None
        return self._resolve()

    async def run(self, context: WorldContext) -> None:
        """Process events and push budget-threshold notifications to the bay channel."""
        self._context = context
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    continue
                if event.channel_id != BAY_CHANNEL_ID:
                    continue
                await self._send_threshold_notifications(context=context)
        except asyncio.CancelledError:
            return

    async def _send_threshold_notifications(self, context: WorldContext) -> None:
        """Notify the bay channel when the communication budget crosses 75% / 100%."""
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
                channel_id=BAY_CHANNEL_ID,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. Communication time: {elapsed} chars exceeded "
                    f"the {budget}s service window."
                ),
            )
            return
        if elapsed >= budget * 0.75 and THRESHOLD_CRITICAL not in self._notified_thresholds:
            self._notified_thresholds.add(THRESHOLD_CRITICAL)
            remaining = budget - elapsed
            await context.send_update_to_channel(
                channel_id=BAY_CHANNEL_ID,
                text=f"CRITICAL: service window almost spent. {remaining} seconds remaining.",
            )

    async def emit_round_terminal_notification(self) -> None:
        """Emit the round's repaired / failed marker to the bay channel."""
        outcome = self.current_outcome()
        if outcome is None:
            return
        if outcome.round_succeeded:
            text = (
                f"{DEVICE_REPAIRED_MARKER}. All {outcome.replacement_count} component(s) replaced."
            )
        else:
            text = f"{DEVICE_FAILED_MARKER}. {outcome.failure_reason}"
        await self._context.send_update_to_channel(channel_id=BAY_CHANNEL_ID, text=text)
