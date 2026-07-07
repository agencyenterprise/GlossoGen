"""World state for the codebreakers scenario.

Tracks per-round target draws, per-agent guess submissions, and
finalized per-round outcomes. The world has no time-based emissions —
``submit_guess`` MCP calls and the scenario's lifecycle hooks drive all
state transitions.
"""

import asyncio
import logging
from typing import Any, NamedTuple

from glossogen.event_logger import EventLogger
from glossogen.runtime.scenario_world import ScenarioWorld, WorldContext
from glossogen.scenarios.codebreakers.events import (
    GuessSubmitted,
    RoundOutcomeRecorded,
    TargetSelected,
)
from glossogen.scenarios.codebreakers.ids import CHRIS_ID, FRIEND_ID
from glossogen.scenarios.codebreakers.referent_pool import RoundTargetSampler

logger = logging.getLogger(__name__)


class RoundOutcome(NamedTuple):
    """Settled outcome for one codebreakers round."""

    round_number: int
    target: str
    friend_guess: str | None
    chris_guess: str | None
    friend_correct: bool
    chris_correct: bool
    success: bool


class CodebreakersWorld(ScenarioWorld):
    """Tracks per-round targets, guesses, and outcomes for codebreakers."""

    _context: WorldContext

    def __init__(self, sampler: RoundTargetSampler) -> None:
        self._sampler = sampler
        self._per_round_guess: dict[int, dict[str, str]] = {}
        self._per_round_correct: dict[int, dict[str, bool]] = {}
        self._outcomes: list[RoundOutcome] = []
        self._finalized_rounds: set[int] = set()
        self._in_postmortem: bool = False

    @property
    def in_postmortem(self) -> bool:
        """True while the pair-only postmortem channel is open for the just-ended round."""
        return self._in_postmortem

    def enter_postmortem(self) -> None:
        """Open the postmortem channel; called from ``on_postmortem_started``."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Close the postmortem channel; called when the next round advances."""
        self._in_postmortem = False

    def outcome_for_round(self, round_number: int) -> RoundOutcome | None:
        """Return the finalized outcome for ``round_number`` or ``None``."""
        for outcome in self._outcomes:
            if outcome.round_number == round_number:
                return outcome
        return None

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def outcomes(self) -> list[RoundOutcome]:
        """All settled per-round outcomes in order."""
        return self._outcomes

    def select_target(self, round_number: int) -> str:
        """Cache and return the deterministic target for ``round_number``."""
        return self._sampler.target_for_round(round_number=round_number)

    def target_for_round(self, round_number: int) -> str:
        """Return the already-cached target for ``round_number``."""
        return self._sampler.target_for_round(round_number=round_number)

    def agent_has_submitted(self, agent_id: str, round_number: int) -> bool:
        """True if ``agent_id`` has already submitted a guess this round."""
        return agent_id in self._per_round_guess.get(round_number, {})

    def has_both_submitted(self, round_number: int) -> bool:
        """True once both Friend and Chris have submitted for this round."""
        submitted = self._per_round_guess.get(round_number, {})
        return FRIEND_ID in submitted and CHRIS_ID in submitted

    def record_guess(
        self,
        agent_id: str,
        round_number: int,
        guess: str,
        correct: bool,
    ) -> None:
        """Persist one agent's per-round guess and correctness flag."""
        if self.agent_has_submitted(agent_id=agent_id, round_number=round_number):
            raise ValueError(
                f"agent {agent_id!r} already submitted a guess for round {round_number}"
            )
        self._per_round_guess.setdefault(round_number, {})[agent_id] = guess
        self._per_round_correct.setdefault(round_number, {})[agent_id] = correct

    def finalize_round(self, round_number: int) -> RoundOutcome:
        """Compute and store the outcome for the just-ended round."""
        if round_number in self._finalized_rounds:
            for outcome in self._outcomes:
                if outcome.round_number == round_number:
                    return outcome
        guesses = self._per_round_guess.get(round_number, {})
        corrects = self._per_round_correct.get(round_number, {})
        friend_guess = guesses.get(FRIEND_ID)
        chris_guess = guesses.get(CHRIS_ID)
        friend_correct = corrects.get(FRIEND_ID, False)
        chris_correct = corrects.get(CHRIS_ID, False)
        success = friend_correct and not chris_correct
        outcome = RoundOutcome(
            round_number=round_number,
            target=self._sampler.target_for_round(round_number=round_number),
            friend_guess=friend_guess,
            chris_guess=chris_guess,
            friend_correct=friend_correct,
            chris_correct=chris_correct,
            success=success,
        )
        self._outcomes.append(outcome)
        self._finalized_rounds.add(round_number)
        return outcome

    async def log_target_selected(
        self,
        round_number: int,
        target: str,
        event_logger: EventLogger,
    ) -> None:
        """Log the per-round ``TargetSelected`` event."""
        await event_logger.log(
            event=TargetSelected(round_number=round_number, target=target),
        )

    async def log_guess_submitted(
        self,
        agent_id: str,
        round_number: int,
        guess: str,
        correct: bool,
        event_logger: EventLogger,
    ) -> None:
        """Log one ``GuessSubmitted`` event."""
        await event_logger.log(
            event=GuessSubmitted(
                round_number=round_number,
                agent_id=agent_id,
                guess=guess,
                correct=correct,
            ),
        )

    async def log_round_outcome(
        self,
        outcome: RoundOutcome,
        event_logger: EventLogger,
    ) -> None:
        """Log the finalized ``RoundOutcomeRecorded`` event."""
        await event_logger.log(
            event=RoundOutcomeRecorded(
                round_number=outcome.round_number,
                target=outcome.target,
                friend_guess=outcome.friend_guess,
                chris_guess=outcome.chris_guess,
                friend_correct=outcome.friend_correct,
                chris_correct=outcome.chris_correct,
                success=outcome.success,
            ),
        )

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Re-seed per-round targets, guesses, and outcomes from a JSONL log.

        ``TargetSelected`` is authoritative for per-round targets (mirrors
        them into the sampler's cache so the seeded RNG isn't required).
        ``GuessSubmitted`` rebuilds the per-agent guess and correctness
        maps. ``RoundOutcomeRecorded`` re-populates the finalized
        outcomes list and finalized-rounds set.
        """
        per_round_guess: dict[int, dict[str, str]] = {}
        per_round_correct: dict[int, dict[str, bool]] = {}
        outcomes_by_round: dict[int, RoundOutcome] = {}
        finalized_rounds: set[int] = set()

        for event in events:
            if isinstance(event, TargetSelected):
                self._sampler.cache_target(
                    round_number=event.round_number,
                    target=event.target,
                )
            elif isinstance(event, GuessSubmitted):
                per_round_guess.setdefault(event.round_number, {})[event.agent_id] = event.guess
                per_round_correct.setdefault(event.round_number, {})[event.agent_id] = event.correct
            elif isinstance(event, RoundOutcomeRecorded):
                outcomes_by_round[event.round_number] = RoundOutcome(
                    round_number=event.round_number,
                    target=event.target,
                    friend_guess=event.friend_guess,
                    chris_guess=event.chris_guess,
                    friend_correct=event.friend_correct,
                    chris_correct=event.chris_correct,
                    success=event.success,
                )
                finalized_rounds.add(event.round_number)

        self._per_round_guess = per_round_guess
        self._per_round_correct = per_round_correct
        self._outcomes = [outcomes_by_round[r] for r in sorted(outcomes_by_round)]
        self._finalized_rounds = finalized_rounds

    async def run(self, context: WorldContext) -> None:
        """Drain world events; codebreakers has no time-based emissions."""
        self._context = context
        try:
            while True:
                await context.next_event()
        except asyncio.CancelledError:
            return
