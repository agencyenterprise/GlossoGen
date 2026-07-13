"""World simulation for the orbital_anomaly scenario.

Monitors cumulative communication character usage on the comm loop for the
current anomaly and pushes real-time status notifications when time
thresholds are crossed. The anomaly is lost when total communication time
exceeds the budget. A vehicle is stabilized only when the astronaut calls
``actuate_panel`` with an action the LLM judge deems adequate for every
cascading stage.

The world holds the per-round state directly (single team). Multi-stage
anomalies reveal one fault at a time: when a stage is resolved, the next
stage's telemetry readout is delivered privately to the Telemetry Officer
and a generic notice is broadcast to the comm loop.
"""

import logging
from typing import NamedTuple

from glossogen.runtime.scenario_world import MessageEvent, ScenarioWorld, WorldContext
from glossogen.scenarios.orbital_anomaly.ids import (
    LINK_CHANNEL_ID,
    NEW_ANOMALY_MARKER,
    POSTMORTEM_CHANNEL_ID,
    TELEMETRY_OFFICER_ID,
    VEHICLE_LOST_MARKER,
    VEHICLE_STABILIZED_MARKER,
)
from glossogen.scenarios.orbital_anomaly.orbital_anomaly_cases import AnomalyCase, AnomalyStage

logger = logging.getLogger(__name__)

_THRESHOLD_LOST = "lost"
_THRESHOLD_CRITICAL = "critical"


class AnomalyOutcome(NamedTuple):
    """Result of a single anomaly after a round completes."""

    case_number: int
    fault_name: str
    stabilized: bool
    characters_used: int
    time_elapsed_seconds: float
    time_budget_seconds: int


class OrbitalAnomalyWorld(ScenarioWorld):
    """Tracks comm-loop usage and pushes real-time anomaly status updates.

    Accumulates character count for the current anomaly. When simulated time
    crosses 75% of the budget or the budget is exceeded, a critical or
    loss-of-system notification is broadcast to the comm loop. The vehicle
    survives only if the astronaut resolves every stage before time runs out.
    """

    _context: WorldContext

    def __init__(self, cases: list[AnomalyCase], postmortem_globally_disabled: bool) -> None:
        self._cases = cases
        self._current_case: AnomalyCase | None = None
        self._in_postmortem: bool = False
        self._postmortem_globally_disabled: bool = postmortem_globally_disabled
        self._current_round_characters: int = 0
        self._vehicle_alive: bool = True
        self._vehicle_stabilized: bool = False
        self._notified_thresholds: set[str] = set()
        self._current_stage_index: int = 0
        self._outcomes: list[AnomalyOutcome] = []

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def current_case(self) -> AnomalyCase | None:
        """The anomaly case for the current round."""
        return self._current_case

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is in a debrief discussion phase."""
        return self._in_postmortem

    @property
    def is_postmortem_disabled(self) -> bool:
        """Whether the debrief has been globally disabled."""
        return self._postmortem_globally_disabled

    def enter_postmortem(self) -> None:
        """Mark the start of a debrief discussion phase."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Mark the end of a debrief discussion phase."""
        self._in_postmortem = False

    def get_globally_disabled_channels(self) -> frozenset[str]:
        """Return the debrief channel when it has been globally disabled."""
        if not self._postmortem_globally_disabled:
            return frozenset()
        return frozenset({POSTMORTEM_CHANNEL_ID})

    def get_current_stage(self) -> AnomalyStage | None:
        """Return the active stage, or None if no case is loaded or all are done."""
        if self._current_case is None:
            return None
        if self._current_stage_index >= len(self._current_case.stages):
            return None
        return self._current_case.stages[self._current_stage_index]

    def is_vehicle_alive(self) -> bool:
        """Whether the current anomaly is still recoverable."""
        return self._vehicle_alive

    def is_vehicle_stabilized(self) -> bool:
        """Whether the current anomaly has been fully resolved."""
        return self._vehicle_stabilized

    async def advance_stage(self) -> AnomalyStage | None:
        """Record the current stage resolved and advance to the next, or finish.

        Returns the next stage when one remains (after delivering its
        telemetry to the Telemetry Officer and a generic notice to the comm
        loop), or None when the anomaly is fully resolved.
        """
        if self._current_case is None:
            return None
        next_index = self._current_stage_index + 1
        if next_index >= len(self._current_case.stages):
            self._vehicle_stabilized = True
            await self._context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=f"{VEHICLE_STABILIZED_MARKER}. All anomalies resolved.",
            )
            return None
        self._current_stage_index = next_index
        next_stage = self._current_case.stages[next_index]
        await self._context.send_update_to_agent(
            agent_id=TELEMETRY_OFFICER_ID,
            text=f"Downlinked telemetry update: {next_stage.telemetry_readout}",
        )
        await self._context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
            text=f"Stage resolved, but {NEW_ANOMALY_MARKER}.",
        )
        return next_stage

    def on_message(self, agent_id: str, channel_id: str, text: str, token_count: int) -> None:
        """Accumulate characters on the comm loop and update state synchronously.

        Called from ``send_message`` before the event is enqueued, so
        ``actuate_panel`` sees correct state immediately. Messages on the
        debrief channel do not count toward the budget.
        """
        _ = agent_id, token_count
        if channel_id != LINK_CHANNEL_ID:
            return
        self._current_round_characters += len(text)
        if self._current_case is None:
            return
        if not self._vehicle_alive:
            return
        if self._vehicle_stabilized:
            return
        if self._current_round_characters > self._current_case.time_budget_seconds:
            self._vehicle_alive = False

    async def on_message_async(self, event: MessageEvent, context: WorldContext) -> None:
        """React to an agent message: push budget/threshold notifications when relevant."""
        _ = context
        if event.channel_id != LINK_CHANNEL_ID:
            return
        await self._send_threshold_notifications()

    async def _send_threshold_notifications(self) -> None:
        """Broadcast a critical or loss notification when a budget threshold is crossed."""
        if self._current_case is None:
            return
        time_elapsed = self._current_round_characters
        budget = self._current_case.time_budget_seconds
        if not self._vehicle_alive and _THRESHOLD_LOST not in self._notified_thresholds:
            self._notified_thresholds.update([_THRESHOLD_LOST, _THRESHOLD_CRITICAL])
            await self._context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=(
                    f"{VEHICLE_LOST_MARKER}. Communication time {time_elapsed}s exceeded the "
                    f"budget of {budget}s."
                ),
            )
            return
        if self._vehicle_stabilized:
            return
        if time_elapsed > budget * 0.75 and _THRESHOLD_CRITICAL not in self._notified_thresholds:
            self._notified_thresholds.add(_THRESHOLD_CRITICAL)
            remaining = budget - time_elapsed
            await self._context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=f"CRITICAL: the anomaly is approaching unrecoverable. {remaining}s remaining.",
            )

    def finalize_round_sync(self, round_number: int) -> None:
        """Reset per-round state and load the case for ``round_number``."""
        self._current_round_characters = 0
        self._vehicle_alive = True
        self._vehicle_stabilized = False
        self._notified_thresholds = set()
        self._current_stage_index = 0
        self._current_case = self._cases[(round_number - 1) % len(self._cases)]

    def mark_round_outcome(self, round_number: int) -> None:
        """Build and append the outcome for the just-ended ``round_number``."""
        _ = round_number
        if self._current_case is None:
            return
        self._outcomes.append(
            AnomalyOutcome(
                case_number=self._current_case.case_number,
                fault_name=self._current_case.fault_name,
                stabilized=self._vehicle_stabilized,
                characters_used=self._current_round_characters,
                time_elapsed_seconds=float(self._current_round_characters),
                time_budget_seconds=self._current_case.time_budget_seconds,
            )
        )

    def previous_outcome(self) -> AnomalyOutcome | None:
        """Return the most recent recorded anomaly outcome, or None before round 1 ends."""
        if not self._outcomes:
            return None
        return self._outcomes[-1]

    async def emit_round_terminal_notification(self) -> None:
        """Emit a terminal notice when the round ends without a prior stabilized/lost marker.

        Covers rounds ending via idle or wall-clock timeout while the anomaly
        is still live but unresolved; the stabilized and budget-exceeded paths
        already broadcast their own markers.
        """
        if self._vehicle_stabilized:
            return
        if _THRESHOLD_LOST in self._notified_thresholds:
            return
        self._notified_thresholds.update([_THRESHOLD_LOST, _THRESHOLD_CRITICAL])
        self._vehicle_alive = False
        await self._context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
            text=f"{VEHICLE_LOST_MARKER}. The anomaly was not resolved before the round ended.",
        )
