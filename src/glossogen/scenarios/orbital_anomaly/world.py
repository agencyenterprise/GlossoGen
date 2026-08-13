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

from glossogen.engine.round_outcome_log import RoundOutcomeLog
from glossogen.engine.round_world import RoundWorld
from glossogen.engine.team_declaration import TeamSpec
from glossogen.runtime.scenario_world import MessageEvent, WorldContext
from glossogen.scenarios.orbital_anomaly.ids import (
    LINK_CHANNEL_ID,
    NEW_ANOMALY_MARKER,
    TELEMETRY_OFFICER_ID,
    VEHICLE_LOST_MARKER,
    VEHICLE_STABILIZED_MARKER,
)
from glossogen.scenarios.orbital_anomaly.orbital_anomaly_cases import AnomalyCase, AnomalyStage
from glossogen.scenarios.orbital_anomaly.team_declaration import TEAM_ID

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


class OrbitalAnomalyWorld(RoundWorld):
    """Tracks comm-loop usage and pushes real-time anomaly status updates.

    Accumulates character count for the current anomaly. When simulated time
    crosses 75% of the budget or the budget is exceeded, a critical or
    loss-of-system notification is broadcast to the comm loop. The vehicle
    survives only if the astronaut resolves every stage before time runs out.
    """

    def __init__(
        self,
        cases: list[AnomalyCase],
        team_specs: tuple[TeamSpec, ...],
        postmortem_channel_ids: frozenset[str],
        postmortem_globally_disabled: bool,
    ) -> None:
        super().__init__(
            team_specs=team_specs,
            round_budget_thresholds=(_THRESHOLD_LOST, _THRESHOLD_CRITICAL),
            postmortem_channel_ids=postmortem_channel_ids,
            postmortem_globally_disabled=postmortem_globally_disabled,
        )
        self._cases = cases
        self._current_case: AnomalyCase | None = None
        self._vehicle_alive: bool = True
        self._vehicle_stabilized: bool = False
        self._current_stage_index: int = 0
        self._outcome_log: RoundOutcomeLog[AnomalyOutcome] = RoundOutcomeLog(team_ids=(TEAM_ID,))

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._world_context

    @property
    def current_case(self) -> AnomalyCase | None:
        """The anomaly case for the current round."""
        return self._current_case

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
            await self._world_context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=f"{VEHICLE_STABILIZED_MARKER}. All anomalies resolved.",
            )
            return None
        self._current_stage_index = next_index
        next_stage = self._current_case.stages[next_index]
        await self._world_context.send_update_to_agent(
            agent_id=TELEMETRY_OFFICER_ID,
            text=f"Downlinked telemetry update: {next_stage.telemetry_readout}",
        )
        await self._world_context.send_update_to_channel(
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
        super().on_message(
            agent_id=agent_id, channel_id=channel_id, text=text, token_count=token_count
        )
        if self.team_for_task_channel(channel_id=channel_id) is None:
            return
        if self._current_case is None:
            return
        if not self._vehicle_alive:
            return
        if self._vehicle_stabilized:
            return
        if self.characters_used(team_id=TEAM_ID) > self._current_case.time_budget_seconds:
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
        time_elapsed = self.characters_used(team_id=TEAM_ID)
        budget = self._current_case.time_budget_seconds
        if not self._vehicle_alive and self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=_THRESHOLD_LOST
        ):
            # The vehicle is lost; the 75% warning has nothing left to warn about.
            self.claim_round_budget_threshold(
                team_id=TEAM_ID, round_budget_threshold=_THRESHOLD_CRITICAL
            )
            await self._world_context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=(
                    f"{VEHICLE_LOST_MARKER}. Communication time {time_elapsed}s exceeded the "
                    f"budget of {budget}s."
                ),
            )
            return
        if self._vehicle_stabilized:
            return
        if time_elapsed > budget * 0.75 and self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=_THRESHOLD_CRITICAL
        ):
            remaining = budget - time_elapsed
            await self._world_context.send_update_to_channel(
                channel_id=LINK_CHANNEL_ID,
                text=f"CRITICAL: the anomaly is approaching unrecoverable. {remaining}s remaining.",
            )

    def finalize_round_sync(self, round_number: int) -> None:
        """Reset per-round state and load the case for ``round_number``."""
        self.begin_round()
        self._vehicle_alive = True
        self._vehicle_stabilized = False
        self._current_stage_index = 0
        self._current_case = self._cases[(round_number - 1) % len(self._cases)]

    def mark_round_outcome(self, round_number: int) -> None:
        """Build and append the outcome for the just-ended ``round_number``."""
        if self._current_case is None:
            return
        # Cases cycle when the run outlasts them, so two rounds can share a
        # case_number. The round is what identifies the outcome.
        self._outcome_log.record(
            team_id=TEAM_ID,
            round_number=round_number,
            outcome=AnomalyOutcome(
                case_number=self._current_case.case_number,
                fault_name=self._current_case.fault_name,
                stabilized=self._vehicle_stabilized,
                characters_used=self.characters_used(team_id=TEAM_ID),
                time_elapsed_seconds=float(self.characters_used(team_id=TEAM_ID)),
                time_budget_seconds=self._current_case.time_budget_seconds,
            ),
        )

    def previous_outcome(self) -> AnomalyOutcome | None:
        """Return the most recent recorded anomaly outcome, or None before round 1 ends."""
        recorded = self._outcome_log.all_for(team_id=TEAM_ID)
        if not recorded:
            return None
        return recorded[-1]

    async def emit_round_terminal_notification(self) -> None:
        """Emit a terminal notice when the round ends without a prior stabilized/lost marker.

        Covers rounds ending via idle or wall-clock timeout while the anomaly
        is still live but unresolved; the stabilized and budget-exceeded paths
        already broadcast their own markers.
        """
        if self._vehicle_stabilized:
            return
        if not self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=_THRESHOLD_LOST
        ):
            return
        # The vehicle is lost; the 75% warning has nothing left to warn about.
        self.claim_round_budget_threshold(
            team_id=TEAM_ID, round_budget_threshold=_THRESHOLD_CRITICAL
        )
        self._vehicle_alive = False
        await self._world_context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
            text=f"{VEHICLE_LOST_MARKER}. The anomaly was not resolved before the round ended.",
        )
