"""Game clock that manages round progression, injection delivery, and termination.

Runs as an asyncio task inside the simulation runtime process. Rounds are an
internal concept — agents never see "round N started." Instead they receive
new information (injections) as if the world is evolving around them.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from schmidt.models.event import RoundAdvanced, RoundEnded, RoundResultRecorded, RunStatus
from schmidt.runtime.agent_session import AgentSession
from schmidt.runtime.scenario_world import WorldContext
from schmidt.runtime.simulation_state import SimulationRuntime
from schmidt.scenario_protocol import SimulationScenario

RoundBoundaryHook = Callable[[int], Awaitable[None]]
"""Callback invoked after a ``RoundAdvanced`` is logged and before injections fire.

Receives the new round number. Used to dispatch scheduled in-run
interventions (agent swaps, postmortem toggles) at the start of a
round so the new state is in place before the round's injections
reach any agent.
"""

logger = logging.getLogger(__name__)

IDLE_CHECK_INTERVAL_SECONDS = 0.5
MIN_ROUND_DURATION_SECONDS = 5.0


class GameClock:
    """Advances rounds based on agent idle state or timeout, and delivers injections."""

    def __init__(
        self,
        scenario: SimulationScenario,
        agent_sessions: dict[str, AgentSession],
        runtime: SimulationRuntime,
        world_context: WorldContext,
        max_rounds: int,
        max_round_duration_seconds: float,
        start_round: int,
        resuming: bool,
        on_round_boundary: RoundBoundaryHook | None,
    ) -> None:
        self._scenario = scenario
        self._agent_sessions = agent_sessions
        self._runtime = runtime
        self._event_logger = runtime.event_logger
        self._world_context = world_context
        self._max_rounds = max_rounds
        self._max_round_duration_seconds = max_round_duration_seconds
        self._start_round = start_round
        self._resuming = resuming
        self._on_round_boundary = on_round_boundary
        runtime.set_current_round(round_number=start_round)
        self._round_start_time = time.monotonic()
        self._last_message_time = time.monotonic()
        self._in_postmortem = False
        self._postmortem_duration_seconds = scenario.get_max_postmortem_duration_seconds()

    def on_message_sent(self) -> None:
        """Called by the simulation runtime whenever a message is sent."""
        self._last_message_time = time.monotonic()

    def _all_agents_idle(self) -> bool:
        """True when every agent is blocked on read_notifications with empty queues.

        Also requires that no agent has any non-blocking tool call in
        flight (``active_non_blocking_calls == 0``) — pydantic-ai
        dispatches parallel tool calls, so a ``read_notifications`` can
        flip ``is_idle`` to True while the same agent's parallel
        ``send_message`` is still mid-execution; ending the round in
        that window drops the in-flight message into the next round.
        """
        for session in self._agent_sessions.values():
            if not session.is_idle:
                return False
            if session.active_non_blocking_calls > 0:
                return False
            if session.has_pending_notifications():
                return False
        return True

    def _phase_timed_out(self) -> bool:
        """Return True if the current phase has exceeded its wall-clock time limit.

        Uses the postmortem duration when in a postmortem phase, otherwise
        the regular round duration. Measured from the phase start time.
        """
        elapsed = time.monotonic() - self._round_start_time
        if self._in_postmortem:
            return elapsed >= self._postmortem_duration_seconds
        return elapsed >= self._max_round_duration_seconds

    async def _advance_round(self, trigger: str) -> None:
        """Increment the round counter, update world state, and deliver injections."""
        self._runtime.set_current_round(round_number=self._runtime.current_round + 1)
        self._round_start_time = time.monotonic()
        self._last_message_time = time.monotonic()

        await self._event_logger.log(
            event=RoundAdvanced(
                round_number=self._runtime.current_round,
                trigger=trigger,
            )
        )
        logger.info(
            "Round advanced to %d (trigger: %s)",
            self._runtime.current_round,
            trigger,
        )

        if self._on_round_boundary is not None:
            await self._on_round_boundary(self._runtime.current_round)

        await self._scenario.on_round_advanced(round_number=self._runtime.current_round)
        self._world_context.signal_round_advanced(round_number=self._runtime.current_round)

        await self._runtime.deliver_round_injections(round_number=self._runtime.current_round)

    async def start_initial_round(self) -> None:
        """Log the first round and deliver injections before agents start.

        Must be called before launching agent tasks so that no events are
        logged with round_number=0.
        """
        self._runtime.set_current_round(round_number=self._start_round)
        self._round_start_time = time.monotonic()
        self._last_message_time = time.monotonic()

        if self._resuming:
            await self._scenario.on_round_advanced(round_number=self._runtime.current_round)
            self._world_context.signal_round_advanced(round_number=self._runtime.current_round)
            logger.info(
                "Game clock resumed at round %d/%d (injections deferred until "
                "after runners + boundary hook)",
                self._runtime.current_round,
                self._max_rounds,
            )
        else:
            await self._event_logger.log(
                event=RoundAdvanced(
                    round_number=self._runtime.current_round,
                    trigger="simulation_start",
                )
            )
            await self._scenario.on_round_advanced(round_number=self._runtime.current_round)
            self._world_context.signal_round_advanced(round_number=self._runtime.current_round)
            await self._runtime.deliver_round_injections(round_number=self._runtime.current_round)
            logger.info(
                "Game clock started. Round %d/%d, injections delivered.",
                self._runtime.current_round,
                self._max_rounds,
            )

    async def dispatch_resume_boundary_events(self) -> None:
        """Fire the round-boundary hook for the resume round, after runners exist.

        On a fresh-start simulation the boundary hook is fired inline by
        ``_advance_round`` after each ``RoundAdvanced``. On resume, the
        initial round was already advanced in the source so
        ``start_initial_round`` cannot fire the hook — agent runners
        don't exist yet, and ``execute_agent_swap`` requires a runner to
        drain. The supervisor calls this method after launching runners
        so any ``scheduled_events`` at ``round_start`` can fire against
        a fully-wired runtime. The scheduler's pre-seeded
        ``_fired_rounds`` set guarantees no double-firing of events that
        already executed in the source's timeline.
        """
        if not self._resuming or self._on_round_boundary is None:
            return
        await self._on_round_boundary(self._runtime.current_round)

    async def deliver_initial_round_injections(self) -> None:
        """Deliver the resume round's injections after boundary events fire.

        On resume the order must match the normal ``_advance_round`` flow:
        boundary hook (which may swap agents) fires first, then injections
        deliver into the post-swap sessions. ``start_initial_round`` defers
        this delivery so the supervisor can sequence
        ``dispatch_resume_boundary_events`` between runner launch and
        injection delivery; without that ordering the round-N injection
        lands in the about-to-be-cancelled predecessor's session and is
        lost to the swapped-in agent.
        """
        if not self._resuming:
            return
        await self._runtime.deliver_round_injections(round_number=self._runtime.current_round)

    async def run(self) -> RunStatus:
        """Run the game clock polling loop. Returns the termination status.

        Assumes ``start_initial_round`` has already been called.
        After each round's game phase, the clock checks whether the scenario
        has postmortem injections. If so, it enters a postmortem phase (with
        its own timeout) before advancing to the next round.
        """
        while True:
            await asyncio.sleep(IDLE_CHECK_INTERVAL_SECONDS)

            if self._scenario.is_finished_early():
                logger.info(
                    "Scenario signalled early finish at round %d",
                    self._runtime.current_round,
                )
                return RunStatus.SCENARIO_COMPLETE

            round_age = time.monotonic() - self._last_message_time
            early_trigger = None
            if not self._in_postmortem:
                early_trigger = self._scenario.get_early_round_end_trigger()
            if early_trigger is not None:
                trigger = early_trigger
                logger.info(
                    "Round %d ending early via scenario trigger: %s",
                    self._runtime.current_round,
                    trigger,
                )
            elif self._all_agents_idle() and round_age >= MIN_ROUND_DURATION_SECONDS:
                trigger = "all_agents_idle"
            elif self._phase_timed_out():
                elapsed = time.monotonic() - self._last_message_time
                phase_label = "Postmortem" if self._in_postmortem else "Round"
                trigger = "postmortem_timeout" if self._in_postmortem else "round_timeout"
                logger.info(
                    "%s %d timed out after %.1f seconds idle",
                    phase_label,
                    self._runtime.current_round,
                    elapsed,
                )
            else:
                continue

            if self._in_postmortem:
                self._in_postmortem = False
                if self._runtime.current_round >= self._max_rounds:
                    logger.info(
                        "All %d rounds complete (after postmortem), ending simulation",
                        self._max_rounds,
                    )
                    return RunStatus.SCENARIO_COMPLETE
                await self._advance_round(trigger=trigger)
            else:
                await self._event_logger.log(
                    event=RoundEnded(
                        round_number=self._runtime.current_round,
                        trigger=trigger,
                    ),
                )
                await self._scenario.on_round_ended(
                    round_number=self._runtime.current_round,
                    trigger=trigger,
                )
                for result in self._scenario.judge_round_result(
                    round_number=self._runtime.current_round,
                    trigger=trigger,
                ):
                    await self._event_logger.log(
                        event=RoundResultRecorded(
                            round_number=self._runtime.current_round,
                            success=result.success,
                            team_id=result.team_id,
                            reason=result.reason,
                        ),
                    )
                if self._runtime.has_postmortem_for_round(round_number=self._runtime.current_round):
                    self._in_postmortem = True
                    self._round_start_time = time.monotonic()
                    self._last_message_time = time.monotonic()
                    await self._runtime.deliver_postmortem_injections(
                        round_number=self._runtime.current_round,
                    )
                else:
                    if self._runtime.current_round >= self._max_rounds:
                        logger.info(
                            "All %d rounds complete, ending simulation",
                            self._max_rounds,
                        )
                        return RunStatus.SCENARIO_COMPLETE
                    if self._scenario.is_finished_early():
                        logger.info(
                            "Scenario signalled early finish after round %d",
                            self._runtime.current_round,
                        )
                        return RunStatus.SCENARIO_COMPLETE
                    await self._advance_round(trigger=trigger)
