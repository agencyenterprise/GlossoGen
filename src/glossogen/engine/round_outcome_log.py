"""Per-team history of round outcomes, one entry per round.

Defines ``RoundOutcomeLog``, which stores whatever record a scenario builds for
a finished round and answers what scenarios ask of it: what
happened in a given round, whether a round has been recorded yet, and the whole
history for a team.

Generic over the record type, because what a round produced is the scenario's
subject matter. The log only guarantees a round is recorded once, which is what
lets a caller ask for an outcome without checking whether an earlier caller
already built it.
"""

from typing import Generic, TypeVar

OutcomeT = TypeVar("OutcomeT")


class RoundOutcomeLog(Generic[OutcomeT]):
    """What each team's rounds produced, in the order they finished."""

    def __init__(self, team_ids: tuple[str, ...]) -> None:
        """Start an empty history for every team."""
        self._outcomes_by_team_id: dict[str, list[OutcomeT]] = {t: [] for t in team_ids}
        self._round_numbers_by_team_id: dict[str, list[int]] = {t: [] for t in team_ids}

    def record(self, team_id: str, round_number: int, outcome: OutcomeT) -> OutcomeT:
        """Store ``outcome`` for a round, or return what was already stored.

        A round's outcome can be asked for from more than one place, and in more
        than one order: a debrief injection wants it as the round closes, and
        the next round's boundary wants it again. Returning the stored record
        rather than appending a second one is what makes those callers agree.
        """
        recorded = self.recorded_for(team_id=team_id, round_number=round_number)
        if recorded is not None:
            return recorded
        self._outcomes_by_team_id[team_id].append(outcome)
        self._round_numbers_by_team_id[team_id].append(round_number)
        return outcome

    def recorded_for(self, team_id: str, round_number: int) -> OutcomeT | None:
        """Return what was stored for one round, or None if nothing was."""
        rounds = self._round_numbers_by_team_id[team_id]
        if round_number not in rounds:
            return None
        return self._outcomes_by_team_id[team_id][rounds.index(round_number)]

    def all_for(self, team_id: str) -> list[OutcomeT]:
        """Return one team's outcomes, oldest first."""
        return list(self._outcomes_by_team_id[team_id])
