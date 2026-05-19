"""World simulation for the surprise_party scenario.

Tracks the fixed party draw, the deterministic per-round friend name
shuffle, the current round's outcome state, whether Chris has decoded the
secret (which terminates the whole simulation), and the history of
resolved round outcomes.
"""

import asyncio
import logging
from typing import Any, Literal, NamedTuple

from schmidt.event_logger import EventLogger
from schmidt.models.event import RoundResultRecorded
from schmidt.runtime.scenario_world import ScenarioWorld, WorldContext
from schmidt.scenarios.surprise_party.events import (
    ChrisCaughtParty,
    FriendIntroduced,
    GuessJudged,
    PartyDecided,
)
from schmidt.scenarios.surprise_party.ids import (
    CHRIS_ID,
    FRIEND_ID,
    TRIGGER_CHRIS_CORRECT,
    TRIGGER_FRIEND_CORRECT,
)
from schmidt.scenarios.surprise_party.party_pool import PartyDraw

logger = logging.getLogger(__name__)


RoundOutcomeLabel = Literal[
    "open",
    "friend_correct",
    "chris_correct",
    "timeout",
]


class RoundOutcome(NamedTuple):
    """Result of a single round once it ends."""

    round_number: int
    label: RoundOutcomeLabel
    friend_name: str


class SurprisePartyWorld(ScenarioWorld):
    """Tracks party draw, friend rotation, and per-round outcomes."""

    _context: WorldContext

    def __init__(
        self,
        party: PartyDraw,
        friend_name_order: tuple[str, ...],
    ) -> None:
        self._party = party
        self._friend_name_order = friend_name_order
        self._current_round_number: int = 0
        self._pending_round_outcome: RoundOutcomeLabel = "open"
        self._chris_caught_party: bool = False
        self._outcomes: list[RoundOutcome] = []

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def party(self) -> PartyDraw:
        """Ground-truth party (where, when)."""
        return self._party

    @property
    def outcomes(self) -> list[RoundOutcome]:
        """All resolved round outcomes in order."""
        return self._outcomes

    @property
    def chris_caught_party(self) -> bool:
        """Whether Chris has decoded the party — terminates the simulation."""
        return self._chris_caught_party

    def friend_name_at_round(self, round_number: int) -> str:
        """Return the rotating Friend's display name for ``round_number``."""
        if round_number < 1 or round_number > len(self._friend_name_order):
            return ""
        return self._friend_name_order[round_number - 1]

    async def record_guess_judged(
        self,
        agent_id: str,
        guess: str,
        correct: bool,
        judge_explanation: str,
        round_number: int,
        event_logger: EventLogger,
    ) -> None:
        """Persist a judged guess and update round-end state if it was correct."""
        agent_display_name = (
            self.friend_name_at_round(round_number=round_number)
            if agent_id == FRIEND_ID
            else agent_id
        )
        await event_logger.log(
            event=GuessJudged(
                round_number=round_number,
                agent_id=agent_id,
                agent_display_name=agent_display_name,
                guess=guess,
                correct=correct,
                judge_explanation=judge_explanation,
            )
        )
        if not correct:
            return
        if agent_id == FRIEND_ID:
            self._pending_round_outcome = "friend_correct"
        elif agent_id == CHRIS_ID:
            self._pending_round_outcome = "chris_correct"
            if not self._chris_caught_party:
                self._chris_caught_party = True
                await event_logger.log(
                    event=ChrisCaughtParty(
                        round_number=round_number,
                        guess=guess,
                    )
                )

    def should_end_round_early(self) -> str | None:
        """Trigger string when the current round should close, or ``None``."""
        if self._pending_round_outcome == "friend_correct":
            return TRIGGER_FRIEND_CORRECT
        if self._pending_round_outcome == "chris_correct":
            return TRIGGER_CHRIS_CORRECT
        return None

    def is_finished(self) -> bool:
        """Whole-sim termination once Chris has decoded the secret.

        Gates on ``finalize_round`` having recorded a ``chris_correct``
        outcome so the game clock emits the ``RoundEnded`` and
        ``RoundResultRecorded`` events for the exposing round before the
        simulation terminates.
        """
        if not self._chris_caught_party:
            return False
        if not self._outcomes:
            return False
        return self._outcomes[-1].label == "chris_correct"

    def finalize_round(self, ending_round_number: int, trigger: str) -> None:
        """Lock in the just-ended round's outcome before the next round opens.

        Called from the scenario's ``on_round_ended`` hook (which fires
        AFTER the ``RoundEnded`` event but BEFORE round advance). Resolves
        ``timeout`` when the round closed without a correct guess.
        """
        label: RoundOutcomeLabel = self._pending_round_outcome
        if label == "open":
            label = "timeout"
        self._outcomes.append(
            RoundOutcome(
                round_number=ending_round_number,
                label=label,
                friend_name=self.friend_name_at_round(round_number=ending_round_number),
            )
        )
        self._pending_round_outcome = "open"
        _ = trigger

    def begin_round(self, new_round_number: int) -> None:
        """Mark ``new_round_number`` as live and reset pending state."""
        self._current_round_number = new_round_number
        self._pending_round_outcome = "open"

    async def log_party_decided(self, event_logger: EventLogger) -> None:
        """Log the ground-truth party once at simulation start (round 0)."""
        await event_logger.log(
            event=PartyDecided(
                round_number=0,
                where=self._party.where,
                when=self._party.when,
            ),
        )

    async def log_friend_introduced(
        self,
        round_number: int,
        event_logger: EventLogger,
    ) -> None:
        """Log the rotating Friend's name for ``round_number``."""
        await event_logger.log(
            event=FriendIntroduced(
                round_number=round_number,
                friend_name=self.friend_name_at_round(round_number=round_number),
            )
        )

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Re-derive the party draw, friend order, and outcomes from a log.

        ``PartyDecided`` and ``FriendIntroduced`` events are authoritative
        on resume. Per-round outcomes are reconstructed by walking
        ``GuessJudged`` events for correct verdicts plus
        ``RoundResultRecorded`` events to detect timeouts.
        """
        seen_friend_names: dict[int, str] = {}
        per_round_outcome: dict[int, RoundOutcomeLabel] = {}
        recorded_rounds: list[int] = []

        for event in events:
            if isinstance(event, PartyDecided):
                self._party = PartyDraw(where=event.where, when=event.when)
            elif isinstance(event, FriendIntroduced):
                seen_friend_names[event.round_number] = event.friend_name
            elif isinstance(event, GuessJudged):
                if not event.correct:
                    continue
                if event.agent_id == FRIEND_ID:
                    per_round_outcome[event.round_number] = "friend_correct"
                elif event.agent_id == CHRIS_ID:
                    per_round_outcome[event.round_number] = "chris_correct"
                    self._chris_caught_party = True
            elif isinstance(event, ChrisCaughtParty):
                self._chris_caught_party = True
            elif isinstance(event, RoundResultRecorded):
                recorded_rounds.append(event.round_number)

        if seen_friend_names:
            length = max(seen_friend_names) if seen_friend_names else 0
            order: list[str] = []
            for r in range(1, length + 1):
                name = seen_friend_names.get(r)
                if name is None:
                    break
                order.append(name)
            if len(order) == length and length > 0:
                tail = list(self._friend_name_order[length:])
                self._friend_name_order = tuple(order + tail)

        self._outcomes = [
            RoundOutcome(
                round_number=r,
                label=per_round_outcome.get(r, "timeout"),
                friend_name=seen_friend_names.get(r, self.friend_name_at_round(round_number=r)),
            )
            for r in sorted(set(recorded_rounds))
        ]

    async def run(self, context: WorldContext) -> None:
        """Consume world events to drain the queue.

        The surprise_party world is deterministic — outcomes are settled by
        the scenario's ``submit_guess`` tool calling ``record_guess_judged``.
        """
        self._context = context
        try:
            while True:
                await context.next_event()
        except asyncio.CancelledError:
            return
