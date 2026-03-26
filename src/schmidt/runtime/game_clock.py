"""Game clock that manages round progression, injection delivery, and termination.

Runs as an asyncio task inside the simulation runtime process. Rounds are an
internal concept — agents never see "round N started." Instead they receive
new information (injections) as if the world is evolving around them.
"""

import asyncio
import logging
import time

from schmidt.event_logger import EventLogger
from schmidt.models.event import InjectionDelivered, RoundAdvanced, RunStatus
from schmidt.runtime.activity_notification import NewInfoNotification
from schmidt.runtime.agent_session import AgentSession
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

IDLE_CHECK_INTERVAL_SECONDS = 0.5


class GameClock:
    """Advances rounds based on agent idle state or timeout, and delivers injections."""

    def __init__(
        self,
        scenario: SimulationScenario,
        agent_sessions: dict[str, AgentSession],
        event_logger: EventLogger,
        max_rounds: int,
        max_round_duration_seconds: float,
        start_round: int,
        last_injected_rounds: dict[str, int],
        resuming: bool,
    ) -> None:
        self._scenario = scenario
        self._agent_sessions = agent_sessions
        self._event_logger = event_logger
        self._max_rounds = max_rounds
        self._max_round_duration_seconds = max_round_duration_seconds
        self._start_round = start_round
        self._last_injected_rounds = last_injected_rounds
        self._resuming = resuming
        self._current_round = 0
        self._last_message_time = time.monotonic()

    def on_message_sent(self) -> None:
        """Called by the simulation runtime whenever a message is sent."""
        self._last_message_time = time.monotonic()

    def _all_agents_idle(self) -> bool:
        """Return True if every agent is blocked on check_messages with no pending notifications."""
        for session in self._agent_sessions.values():
            if not session.is_idle:
                return False
            if session.has_pending_notifications():
                return False
        return True

    def _round_timed_out(self) -> bool:
        """Return True if the current round has exceeded its time limit."""
        elapsed = time.monotonic() - self._last_message_time
        return elapsed >= self._max_round_duration_seconds

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
            if injection_text is None:
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
        """Increment the round counter and deliver injections for the new round."""
        self._current_round += 1
        self._last_message_time = time.monotonic()

        await self._event_logger.log(
            event=RoundAdvanced(
                new_round_number=self._current_round,
                trigger=trigger,
            )
        )
        logger.info(
            "Round advanced to %d (trigger: %s)",
            self._current_round,
            trigger,
        )

        await self._deliver_injections(round_number=self._current_round)

    async def run(self) -> RunStatus:
        """Run the game clock loop. Returns the termination status.

        On fresh runs, logs ``RoundAdvanced`` and delivers round-1 injections.
        On resumed runs, starts from ``start_round`` without re-delivering.
        """
        self._current_round = self._start_round
        self._last_message_time = time.monotonic()

        if self._resuming:
            logger.info(
                "Game clock resumed at round %d/%d",
                self._current_round,
                self._max_rounds,
            )
        else:
            await self._event_logger.log(
                event=RoundAdvanced(
                    new_round_number=self._current_round,
                    trigger="simulation_start",
                )
            )
            await self._deliver_injections(round_number=self._current_round)
            logger.info(
                "Game clock started. Round %d/%d, injections delivered.",
                self._current_round,
                self._max_rounds,
            )

        while True:
            await asyncio.sleep(IDLE_CHECK_INTERVAL_SECONDS)

            if self._all_agents_idle():
                trigger = "all_agents_idle"
            elif self._round_timed_out():
                elapsed = time.monotonic() - self._last_message_time
                trigger = "round_timeout"
                logger.info(
                    "Round %d timed out after %.1f seconds",
                    self._current_round,
                    elapsed,
                )
            else:
                continue

            if self._current_round >= self._max_rounds:
                logger.info(
                    "All %d rounds complete, ending simulation",
                    self._max_rounds,
                )
                return RunStatus.SCENARIO_COMPLETE

            await self._advance_round(trigger=trigger)
