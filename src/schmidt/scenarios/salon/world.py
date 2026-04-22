"""World simulation for the Salon covert broadcast scenario.

Tracks per-round state: the current directive drawn from the fixed
catalogue, the Confidant's pending decode guess, the Inquisitor's pending
intercept guesses (up to ``inquisitor_guesses_per_round``), and the
history of resolved round outcomes. Round correctness is determined by
exact directive id match. The Salon world does not push time-based
threshold notifications — it only consumes events to drain the queue.
"""

import asyncio
import logging
from typing import NamedTuple

from schmidt.runtime.scenario_world import ScenarioWorld, WorldContext

logger = logging.getLogger(__name__)


class RoundOutcome(NamedTuple):
    """Result of a single round after both sides' guesses are resolved.

    ``full_success`` is the only outcome that rewards the pair: the
    Confidant decoded the directive and the Inquisitor did not.
    """

    round_number: int
    confidant_correct: bool
    inquisitor_correct: bool
    full_success: bool


class SalonWorld(ScenarioWorld):
    """Tracks per-round directive, guesses, and outcomes for the Salon scenario.

    The scenario generates the ``directive_sequence`` once at construction
    time from the seeded knobs and hands it to this world. The scenario's
    ``on_round_advanced`` hook calls ``finalize_round_sync`` so outcomes
    become available to the next round's injections.
    """

    _context: WorldContext

    def __init__(
        self,
        directive_sequence: list[str],
        inquisitor_guesses_per_round: int,
    ) -> None:
        self._directive_sequence = list(directive_sequence)
        self._inquisitor_guesses_per_round = inquisitor_guesses_per_round
        self._current_round_number: int = 0
        self._in_postmortem: bool = False
        self._pending_confidant_guess: str | None = None
        self._pending_inquisitor_guesses: list[str] = []
        self._outcomes: list[RoundOutcome] = []

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is currently in a postmortem discussion phase."""
        return self._in_postmortem

    @property
    def outcomes(self) -> list[RoundOutcome]:
        """All resolved round outcomes in order."""
        return self._outcomes

    @property
    def inquisitor_guess_limit(self) -> int:
        """Maximum intercept submissions allowed per round."""
        return self._inquisitor_guesses_per_round

    def enter_postmortem(self) -> None:
        """Mark the start of a postmortem discussion phase."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Mark the end of a postmortem discussion phase."""
        self._in_postmortem = False

    def get_directive_for_round(self, round_number: int) -> str | None:
        """Return the directive id drawn for ``round_number``, or None if out of range."""
        if round_number < 1 or round_number > len(self._directive_sequence):
            return None
        return self._directive_sequence[round_number - 1]

    def record_confidant_guess(self, directive_id: str) -> None:
        """Store the Confidant's latest decode guess for the current round."""
        self._pending_confidant_guess = directive_id

    def record_inquisitor_guess(self, directive_id: str) -> None:
        """Append an intercept guess from the Inquisitor for the current round."""
        self._pending_inquisitor_guesses.append(directive_id)

    def inquisitor_submission_count(self) -> int:
        """Return how many intercept guesses the Inquisitor has made this round."""
        return len(self._pending_inquisitor_guesses)

    def compute_outcome_if_needed(self, round_number: int) -> RoundOutcome | None:
        """Resolve and cache the outcome for ``round_number`` if not already done.

        Returns the cached outcome on subsequent calls. If ``round_number``
        does not match the current round and no cached outcome exists,
        returns None — the pending guess state is only meaningful for the
        round currently in play.
        """
        if round_number < 1:
            return None
        for existing in self._outcomes:
            if existing.round_number == round_number:
                return existing
        if round_number != self._current_round_number:
            return None
        directive = self.get_directive_for_round(round_number=round_number)
        if directive is None:
            return None

        confidant_correct = self._pending_confidant_guess == directive
        inquisitor_correct = directive in self._pending_inquisitor_guesses
        outcome = RoundOutcome(
            round_number=round_number,
            confidant_correct=confidant_correct,
            inquisitor_correct=inquisitor_correct,
            full_success=confidant_correct and not inquisitor_correct,
        )
        self._outcomes.append(outcome)
        return outcome

    def finalize_round_sync(self, new_round_number: int) -> None:
        """Resolve the previous round (if any) and advance to ``new_round_number``.

        Called by the scenario's ``on_round_advanced`` hook before the
        next round's injections are rendered. Idempotent with respect to
        ``compute_outcome_if_needed`` for the same round.
        """
        if new_round_number >= 2:
            self.compute_outcome_if_needed(round_number=new_round_number - 1)
        self._current_round_number = new_round_number
        self._pending_confidant_guess = None
        self._pending_inquisitor_guesses = []

    async def run(self, context: WorldContext) -> None:
        """Consume world events to keep the queue drained.

        The Salon world has no time-based notifications to emit; it simply
        waits for events and discards them. The ``CancelledError`` path
        is the normal shutdown trigger.
        """
        self._context = context
        try:
            while True:
                await context.next_event()
        except asyncio.CancelledError:
            return
