"""Per-team round state, the outcome a round leaves, and how a round is scored.

A team is correct only when every member submitted the round's answer, within
the character budget when one is set. Among correct teams, the fewest link
characters wins. A simulated opponent is ranked by the same rule. ``score_round``
is the one place that rule lives, read by the live world and by the event-log
reconstruction alike.
"""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import NamedTuple, Self

from glossogen.engine.fewest_characters_winner import fewest_characters_winners
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject
from glossogen.scenarios.spot_the_intersection.ids import TEAM_B_ID


class IntersectionOutcome(NamedTuple):
    """One team's result for one round.

    ``agreed`` is whether every member submitted and all submitted the same
    object, right or wrong. ``won`` holds only in two-team runs, for the
    correct team (or tied teams) with the fewest characters. The ``opponent_*``
    fields describe the other team and are ``None`` with one team;
    ``opponent_simulated`` says that team was simulated rather than played.
    """

    round_number: int
    team_id: str
    members_required: int
    members_submitted: int
    members_correct: int
    agreed: bool
    budget_exceeded: bool
    characters_used: int
    correct: bool
    won: bool
    competitive: bool
    opponent_correct: bool | None
    opponent_characters: int | None
    opponent_simulated: bool


class TeamSnapshot(NamedTuple):
    """A team's end-of-round state, ready to score."""

    team_id: str
    members_required: int
    members_submitted: int
    members_correct: int
    agreed: bool
    budget_exceeded: bool
    characters: int

    @property
    def correct(self) -> bool:
        """Every member submitted the answer, within budget."""
        return self.members_correct == self.members_required and not self.budget_exceeded


@dataclass
class TeamState:
    """What the world tracks for one team during a round."""

    team_id: str
    link_channel_id: str
    member_agent_ids: tuple[str, ...]
    submissions_by_agent: dict[str, BoardObject]
    locked: bool
    characters_at_lock: int
    round_budget_exceeded: bool

    @classmethod
    def fresh(cls, team_id: str, link_channel_id: str, member_agent_ids: tuple[str, ...]) -> Self:
        """A team at the start of a round: nothing submitted, nothing spent."""
        return cls(
            team_id=team_id,
            link_channel_id=link_channel_id,
            member_agent_ids=member_agent_ids,
            submissions_by_agent={},
            locked=False,
            characters_at_lock=0,
            round_budget_exceeded=False,
        )

    @property
    def members_required(self) -> int:
        """Every member must submit."""
        return len(self.member_agent_ids)

    def snapshot(self, answer: BoardObject, characters_used: int) -> TeamSnapshot:
        """This team's state for scoring.

        A locked team is charged what it had spent when its last member
        submitted, so nothing said afterwards changes its score.
        """
        characters = characters_used
        if self.locked:
            characters = self.characters_at_lock
        return snapshot_from_submissions(
            team_id=self.team_id,
            members_required=self.members_required,
            submissions=list(self.submissions_by_agent.values()),
            answer=answer,
            budget_exceeded=self.round_budget_exceeded,
            characters=characters,
        )

    def reset_for_new_round(self) -> None:
        """Clear the submissions, the lock and the budget flag."""
        self.submissions_by_agent = {}
        self.locked = False
        self.characters_at_lock = 0
        self.round_budget_exceeded = False


def snapshot_from_submissions(
    team_id: str,
    members_required: int,
    submissions: Sequence[BoardObject],
    answer: BoardObject,
    budget_exceeded: bool,
    characters: int,
) -> TeamSnapshot:
    """Summarise one team's submissions against the round's answer."""
    return TeamSnapshot(
        team_id=team_id,
        members_required=members_required,
        members_submitted=len(submissions),
        members_correct=sum(1 for submission in submissions if submission == answer),
        agreed=len(submissions) == members_required and len(set(submissions)) == 1,
        budget_exceeded=budget_exceeded,
        characters=characters,
    )


_SHARE_STEPS = 1000


class SimulatedOpponent(NamedTuple):
    """The simulated Team B: its share of Team A's characters lies in ``low``..``high``."""

    seed: int
    low: Fraction
    high: Fraction

    def share(self, round_number: int) -> Fraction:
        """The round's share, one of the range's thousandths, picked from the seed and the round.

        A fresh generator per round makes the share a function of the round alone,
        so the live world and a replay of the log score a round the same way.
        """
        rng = random.Random(f"spot_the_intersection:{self.seed}:{round_number}:opponent")
        step = rng.randrange(_SHARE_STEPS + 1)
        return self.low + (self.high - self.low) * Fraction(step, _SHARE_STEPS)


def simulated_opponent_for(
    seed: int, share: float | tuple[float, float] | None
) -> SimulatedOpponent | None:
    """The simulated Team B a run's knobs ask for, or ``None`` when both teams play.

    A number fixes the share; a ``(low, high)`` pair is the range each round's
    share is drawn from. Values are read as the decimals the knob holds, so 0.8
    is four fifths rather than its binary approximation.
    """
    if share is None:
        return None
    if isinstance(share, tuple):
        low, high = share
    else:
        low = high = share
    return SimulatedOpponent(seed=seed, low=Fraction(str(low)), high=Fraction(str(high)))


def simulated_team_b(played: TeamSnapshot, share: Fraction) -> TeamSnapshot:
    """The Team B a lone Team A is scored against: always correct, ``share`` of its characters.

    The share is exact and the result rounded down, so 0.8 of 203 characters is
    162 and binary rounding never moves it across a whole number.
    """
    return TeamSnapshot(
        team_id=TEAM_B_ID,
        members_required=played.members_required,
        members_submitted=played.members_required,
        members_correct=played.members_required,
        agreed=True,
        budget_exceeded=False,
        characters=math.floor(share * played.characters),
    )


def score_round(
    round_number: int,
    snapshots: Sequence[TeamSnapshot],
    competitive: bool,
    simulated_opponent: SimulatedOpponent | None,
) -> tuple[IntersectionOutcome, ...]:
    """Apply the correctness gate, then fewest-characters-wins, in team order.

    With ``simulated_opponent`` set, ``snapshots`` holds Team A alone, and a
    simulated Team B joins the ranking at the round's share of Team A's
    characters; only Team A's outcome is returned.
    """
    ranked = list(snapshots)
    if simulated_opponent is not None:
        if len(snapshots) != 1:
            raise ValueError(
                f"a simulated opponent plays against one team (got {len(snapshots)} teams)"
            )
        ranked.append(
            simulated_team_b(played=snapshots[0], share=simulated_opponent.share(round_number))
        )
    winners = fewest_characters_winners(
        characters_by_eligible_team_id={
            snapshot.team_id: snapshot.characters for snapshot in ranked if snapshot.correct
        }
    )
    outcomes: list[IntersectionOutcome] = []
    for snapshot in snapshots:
        opponent = _opponent_of(snapshot=snapshot, snapshots=ranked, competitive=competitive)
        opponent_correct: bool | None = None
        opponent_characters: int | None = None
        if opponent is not None:
            opponent_correct = opponent.correct
            opponent_characters = opponent.characters
        outcomes.append(
            IntersectionOutcome(
                round_number=round_number,
                team_id=snapshot.team_id,
                members_required=snapshot.members_required,
                members_submitted=snapshot.members_submitted,
                members_correct=snapshot.members_correct,
                agreed=snapshot.agreed,
                budget_exceeded=snapshot.budget_exceeded,
                characters_used=snapshot.characters,
                correct=snapshot.correct,
                won=competitive and snapshot.team_id in winners,
                competitive=competitive,
                opponent_correct=opponent_correct,
                opponent_characters=opponent_characters,
                opponent_simulated=simulated_opponent is not None,
            )
        )
    return tuple(outcomes)


def _opponent_of(
    snapshot: TeamSnapshot, snapshots: Sequence[TeamSnapshot], competitive: bool
) -> TeamSnapshot | None:
    """The other team's snapshot in a two-team run."""
    if not competitive:
        return None
    others = [other for other in snapshots if other.team_id != snapshot.team_id]
    if not others:
        return None
    return others[0]


def outcome_reason(outcome: IntersectionOutcome) -> str:
    """A one-line reason for the round result the clock records.

    An exhausted budget comes first, since it can end the round before every
    member has submitted. Against a simulated opponent the reason names it and
    its count; the viewers are never told it was simulated.
    """
    counts = (
        f"{outcome.members_correct}/{outcome.members_required} submitted the answer, "
        f"{outcome.characters_used} chars"
    )
    if outcome.opponent_simulated:
        counts = f"{counts}, simulated opponent {outcome.opponent_characters} chars"
    if outcome.budget_exceeded:
        return f"over budget ({counts})"
    if outcome.members_submitted < outcome.members_required:
        return (
            f"only {outcome.members_submitted}/{outcome.members_required} members submitted "
            f"({counts})"
        )
    if outcome.won:
        return f"won ({counts})"
    if outcome.correct and outcome.competitive:
        return f"correct but the other team used fewer characters ({counts})"
    if outcome.correct:
        return f"correct ({counts})"
    if not outcome.agreed:
        return f"members submitted different objects ({counts})"
    return f"every member submitted the same wrong object ({counts})"
