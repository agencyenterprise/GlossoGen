"""Game clock that manages round progression, injection delivery, and termination.

Runs as an asyncio task inside the simulation runtime process. Rounds are an
internal concept — agents never see "round N started." Instead they receive
new information (injections) as if the world is evolving around them.
"""

import asyncio
import logging
import time

from schmidt.event_logger import EventLogger
from schmidt.models.event import (
    InjectionDelivered,
    PostmortemStarted,
    RoundAdvanced,
    RoundEnded,
    RunStatus,
)
from schmidt.runtime.activity_notification import NewInfoNotification
from schmidt.runtime.agent_session import AgentSession
from schmidt.runtime.scenario_world import WorldContext
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

IDLE_CHECK_INTERVAL_SECONDS = 0.5
MIN_ROUND_DURATION_SECONDS = 5.0


class GameClock:
    """Advances rounds based on agent idle state or timeout, and delivers injections."""

    def __init__(
        self,
        scenario: SimulationScenario,
        agent_sessions: dict[str, AgentSession],
        event_logger: EventLogger,
        world_context: WorldContext,
        max_rounds: int,
        max_round_duration_seconds: float,
        start_round: int,
        last_injected_rounds: dict[str, int],
        resuming: bool,
    ) -> None:
        self._scenario = scenario
        self._agent_sessions = agent_sessions
        self._event_logger = event_logger
        self._world_context = world_context
        self._max_rounds = max_rounds
        self._max_round_duration_seconds = max_round_duration_seconds
        self._start_round = start_round
        self._last_injected_rounds = last_injected_rounds
        self._resuming = resuming
        self._current_round = self._start_round
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

    def _has_postmortem(self, round_number: int) -> bool:
        """Check whether any agent has a postmortem injection for the given round."""
        for agent_id in self._agent_sessions:
            injection = self._scenario.get_postmortem_injection(
                round_number=round_number,
                agent_id=agent_id,
            )
            if injection is not None:
                return True
        return False

    async def _deliver_postmortem_injections(self, round_number: int) -> None:
        """Enter the postmortem phase and deliver postmortem injections to agents."""
        self._in_postmortem = True
        self._round_start_time = time.monotonic()
        self._last_message_time = time.monotonic()

        await self._event_logger.log(
            event=PostmortemStarted(round_number=round_number),
        )
        self._scenario.on_postmortem_started(round_number=round_number)
        logger.info("Postmortem started for round %d", round_number)

        for agent_id, session in self._agent_sessions.items():
            injection_text = self._scenario.get_postmortem_injection(
                round_number=round_number,
                agent_id=agent_id,
            )
            if not injection_text:
                continue

            session.push_notification(
                notification=NewInfoNotification(text=injection_text),
            )
            await self._event_logger.log(
                event=InjectionDelivered(
                    agent_id=agent_id,
                    round_number=round_number,
                    text=injection_text,
                ),
            )
            logger.debug(
                "Postmortem injection delivered to %s for round %d",
                agent_id,
                round_number,
            )

    async def _deliver_injections(self, round_number: int) -> None:
        """Push injection notifications to agents that have one for this round.

        Skips agents that already received an injection for this round
        (tracked via ``_last_injected_rounds``, populated during resume).
        """
        for agent_id, session in self._agent_sessions.items():
            already_injected_round = self._last_injected_rounds.get(agent_id, 0)
            if round_number <= already_injected_round:
                logger.debug(
                    "Skipping injection for %s round %d (already delivered up to round %d)",
                    agent_id,
                    round_number,
                    already_injected_round,
                )
                continue

            injection_text = self._scenario.get_injection(
                round_number=round_number,
                agent_id=agent_id,
            )
            if not injection_text:
                continue

            session.push_notification(
                notification=NewInfoNotification(text=injection_text),
            )
            await self._event_logger.log(
                event=InjectionDelivered(
                    agent_id=agent_id,
                    round_number=round_number,
                    text=injection_text,
                )
            )
            logger.debug(
                "Injection delivered to %s for round %d",
                agent_id,
                round_number,
            )

    async def _advance_round(self, trigger: str) -> None:
        """Increment the round counter, update world state, and deliver injections."""
        self._current_round += 1
        self._round_start_time = time.monotonic()
        self._last_message_time = time.monotonic()

        await self._event_logger.log(
            event=RoundAdvanced(
                round_number=self._current_round,
                trigger=trigger,
            )
        )
        logger.info(
            "Round advanced to %d (trigger: %s)",
            self._current_round,
            trigger,
        )

        await self._scenario.on_round_advanced(round_number=self._current_round)
        self._world_context.signal_round_advanced(round_number=self._current_round)

        await self._deliver_injections(round_number=self._current_round)

    async def start_initial_round(self) -> None:
        """Log the first round and deliver injections before agents start.

        Must be called before launching agent tasks so that no events are
        logged with round_number=0.
        """
        self._current_round = self._start_round
        self._round_start_time = time.monotonic()
        self._last_message_time = time.monotonic()

        if self._resuming:
            await self._scenario.on_round_advanced(round_number=self._current_round)
            self._world_context.signal_round_advanced(round_number=self._current_round)
            await self._deliver_injections(round_number=self._current_round)
            logger.info(
                "Game clock resumed at round %d/%d",
                self._current_round,
                self._max_rounds,
            )
        else:
            await self._event_logger.log(
                event=RoundAdvanced(
                    round_number=self._current_round,
                    trigger="simulation_start",
                )
            )
            await self._scenario.on_round_advanced(round_number=self._current_round)
            self._world_context.signal_round_advanced(round_number=self._current_round)
            await self._deliver_injections(round_number=self._current_round)
            logger.info(
                "Game clock started. Round %d/%d, injections delivered.",
                self._current_round,
                self._max_rounds,
            )

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
                    self._current_round,
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
                    self._current_round,
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
                    self._current_round,
                    elapsed,
                )
            else:
                continue

            if self._in_postmortem:
                self._in_postmortem = False
                if self._current_round >= self._max_rounds:
                    logger.info(
                        "All %d rounds complete (after postmortem), ending simulation",
                        self._max_rounds,
                    )
                    return RunStatus.SCENARIO_COMPLETE
                await self._advance_round(trigger=trigger)
            else:
                await self._event_logger.log(
                    event=RoundEnded(
                        round_number=self._current_round,
                        trigger=trigger,
                    ),
                )
                await self._scenario.on_round_ended(
                    round_number=self._current_round,
                    trigger=trigger,
                )
                if self._has_postmortem(round_number=self._current_round):
                    await self._deliver_postmortem_injections(
                        round_number=self._current_round,
                    )
                else:
                    if self._current_round >= self._max_rounds:
                        logger.info(
                            "All %d rounds complete, ending simulation",
                            self._max_rounds,
                        )
                        return RunStatus.SCENARIO_COMPLETE
                    await self._advance_round(trigger=trigger)
