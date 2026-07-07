"""World simulation for the surprise_party scenario.

Tracks the per-round friend identity, the active surprise party (which
gets re-drawn every time Chris catches the current one), and the history
of resolved round outcomes. The world is otherwise deterministic — the
``submit_guess`` MCP tool drives all state transitions via
``record_guess_judged``.
"""

import asyncio
import logging
from typing import Any, Literal, NamedTuple

from glossogen.event_logger import EventLogger
from glossogen.models.event import RoundResultRecorded
from glossogen.runtime.scenario_world import ScenarioWorld, WorldContext
from glossogen.scenarios.surprise_party.events import (
    ChrisCaughtParty,
    FriendIntroduced,
    GuessJudged,
    PartyDecided,
)
from glossogen.scenarios.surprise_party.ids import CHRIS_ID, FRIEND_ID
from glossogen.scenarios.surprise_party.party_pool import PartyDraw, PartyRng

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
    party: PartyDraw


class PartyEra(NamedTuple):
    """One ``(where, when)`` draw and the round it became active."""

    first_round_active: int
    party: PartyDraw


class SurprisePartyWorld(ScenarioWorld):
    """Tracks party history, friend rotation, and per-round outcomes."""

    _context: WorldContext

    def __init__(
        self,
        party_rng: PartyRng,
        friend_name_order: tuple[str, ...],
    ) -> None:
        self._party_rng = party_rng
        initial_party = party_rng.draw_distinct_from(previous=None)
        self._party_history: list[PartyEra] = [
            PartyEra(first_round_active=1, party=initial_party),
        ]
        self._friend_name_order = friend_name_order
        self._pending_round_outcome: RoundOutcomeLabel = "open"
        self._outcomes: list[RoundOutcome] = []

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def outcomes(self) -> list[RoundOutcome]:
        """All resolved round outcomes in order."""
        return self._outcomes

    @property
    def party_history(self) -> list[PartyEra]:
        """Every ``(first_round_active, PartyDraw)`` era in order."""
        return self._party_history

    def party_for_round(self, round_number: int) -> PartyDraw:
        """Return the party that's active during ``round_number``."""
        active = self._party_history[0].party
        for era in self._party_history:
            if era.first_round_active <= round_number:
                active = era.party
            else:
                break
        return active

    def friend_name_at_round(self, round_number: int) -> str:
        """Return the rotating Friend's display name for ``round_number``."""
        if round_number < 1 or round_number > len(self._friend_name_order):
            return ""
        return self._friend_name_order[round_number - 1]

    def begin_party_era(self, first_round_active: int) -> PartyDraw:
        """Draw a fresh party and start a new era at ``first_round_active``.

        Idempotent: a second call for the same ``first_round_active``
        returns the existing era's party without re-drawing.
        """
        for era in self._party_history:
            if era.first_round_active == first_round_active:
                return era.party
        previous = self._party_history[-1].party
        new_party = self._party_rng.draw_distinct_from(previous=previous)
        self._party_history.append(PartyEra(first_round_active=first_round_active, party=new_party))
        return new_party

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
        if agent_id == CHRIS_ID:
            # Chris exposure is sticky for the round: once he's caught the
            # party, a later friend-correct guess cannot rescue the round.
            self._pending_round_outcome = "chris_correct"
            await event_logger.log(
                event=ChrisCaughtParty(
                    round_number=round_number,
                    guess=guess,
                )
            )
            return
        if agent_id == FRIEND_ID and self._pending_round_outcome != "chris_correct":
            self._pending_round_outcome = "friend_correct"

    def should_end_round_early(self) -> str | None:
        """Trigger string when the current round should close, or ``None``."""
        if self._pending_round_outcome == "friend_correct":
            return "friend_correct"
        if self._pending_round_outcome == "chris_correct":
            return "chris_correct"
        return None

    def finalize_round(self, ending_round_number: int) -> RoundOutcomeLabel:
        """Lock in the just-ended round's outcome and return its label.

        Called from the scenario's ``on_round_ended`` hook. Resolves
        ``timeout`` when the round closed without a correct guess and
        clears ``_pending_round_outcome``.
        """
        label: RoundOutcomeLabel = self._pending_round_outcome
        if label == "open":
            label = "timeout"
        self._outcomes.append(
            RoundOutcome(
                round_number=ending_round_number,
                label=label,
                friend_name=self.friend_name_at_round(round_number=ending_round_number),
                party=self.party_for_round(round_number=ending_round_number),
            )
        )
        self._pending_round_outcome = "open"
        return label

    async def log_party_decided(
        self,
        party: PartyDraw,
        round_number: int,
        event_logger: EventLogger,
    ) -> None:
        """Log a ``PartyDecided`` event for an era's ``(where, when)``."""
        await event_logger.log(
            event=PartyDecided(
                round_number=round_number,
                where=party.where,
                when=party.when,
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
        """Re-derive party history, friend order, and outcomes from a JSONL log.

        ``PartyDecided`` events are authoritative for party history (one
        per era, each carrying the round it became active).
        ``FriendIntroduced`` events are authoritative for the per-round
        friend name. Per-round outcomes are inferred from
        ``GuessJudged``/``RoundResultRecorded``.
        """
        seen_friend_names: dict[int, str] = {}
        per_round_outcome: dict[int, RoundOutcomeLabel] = {}
        recorded_rounds: list[int] = []
        observed_parties: list[PartyEra] = []

        for event in events:
            if isinstance(event, PartyDecided):
                first_round = event.round_number if event.round_number >= 1 else 1
                observed_parties.append(
                    PartyEra(
                        first_round_active=first_round,
                        party=PartyDraw(where=event.where, when=event.when),
                    )
                )
            elif isinstance(event, FriendIntroduced):
                seen_friend_names[event.round_number] = event.friend_name
            elif isinstance(event, GuessJudged):
                if not event.correct:
                    continue
                if event.agent_id == CHRIS_ID:
                    per_round_outcome[event.round_number] = "chris_correct"
                elif event.agent_id == FRIEND_ID and (
                    per_round_outcome.get(event.round_number) != "chris_correct"
                ):
                    per_round_outcome[event.round_number] = "friend_correct"
            elif isinstance(event, RoundResultRecorded):
                recorded_rounds.append(event.round_number)

        if observed_parties:
            observed_parties.sort(key=lambda era: era.first_round_active)
            self._party_history = observed_parties

        if seen_friend_names:
            length = max(seen_friend_names)
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
                party=self.party_for_round(round_number=r),
            )
            for r in sorted(set(recorded_rounds))
        ]

    async def run(self, context: WorldContext) -> None:
        """Drain world events; surprise_party has no time-based emissions."""
        self._context = context
        try:
            while True:
                await context.next_event()
        except asyncio.CancelledError:
            return
