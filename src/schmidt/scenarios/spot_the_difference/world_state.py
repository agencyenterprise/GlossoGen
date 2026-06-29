"""Mutable per-team state, immutable outcome types, and round scoring.

The world holds one ``TeamState`` per team (solo mode keeps one; two-team
mode keeps two). Each ``TeamState`` carries the running link-channel character
count, the team's locked submission verdict, and the rolling list of finished
``DiffOutcome`` entries. ``build_round_outcomes`` is the single place the
correctness gate and the fewest-characters-wins comparison live, shared by the
live world and the event-log reconstructor.
"""

from dataclasses import dataclass, field
from typing import NamedTuple


class DiffOutcome(NamedTuple):
    """Result of one round for one team.

    ``eligible`` is the correctness gate (submitted, every planted difference
    found, no false positives). ``won`` is True only in two-team mode for the
    eligible team(s) with the fewest characters. The ``opponent_*`` fields
    describe the single other team in two-team mode and are ``None`` in solo
    mode.
    """

    case_number: int
    team_id: str
    total_differences: int
    found_count: int
    false_positive_count: int
    found_all: bool
    submitted: bool
    characters_used: int
    eligible: bool
    won: bool
    competitive: bool
    opponent_found_all: bool | None
    opponent_eligible: bool | None
    opponent_characters: int | None


class SubmissionSnapshot(NamedTuple):
    """A team's end-of-round submission state used to score the round."""

    submitted: bool
    found_all: bool
    false_positive_count: int
    found_count: int
    characters: int


@dataclass
class TeamState:
    """All per-team mutable state the world tracks for one team."""

    team_id: str
    link_channel_id: str
    current_round_characters: int = 0
    submitted: bool = False
    verdict_recorded: bool = False
    submitted_found_all: bool = False
    submitted_false_positives: int = 0
    submitted_found_count: int = 0
    characters_at_submission: int = 0
    round_outcome_marked: bool = False
    outcomes: list[DiffOutcome] = field(default_factory=list[DiffOutcome])

    def snapshot(self) -> SubmissionSnapshot:
        """Capture this team's end-of-round submission state."""
        if self.submitted:
            characters = self.characters_at_submission
        else:
            characters = self.current_round_characters
        return SubmissionSnapshot(
            submitted=self.submitted,
            found_all=self.submitted_found_all,
            false_positive_count=self.submitted_false_positives,
            found_count=self.submitted_found_count,
            characters=characters,
        )

    def reset_for_new_round(self) -> None:
        """Clear all per-round counters and the locked submission."""
        self.current_round_characters = 0
        self.submitted = False
        self.verdict_recorded = False
        self.submitted_found_all = False
        self.submitted_false_positives = 0
        self.submitted_found_count = 0
        self.characters_at_submission = 0
        self.round_outcome_marked = False


def _is_eligible(snapshot: SubmissionSnapshot) -> bool:
    """Whether a snapshot passes the correctness gate."""
    return snapshot.submitted and snapshot.found_all and snapshot.false_positive_count == 0


def build_round_outcomes(
    case_number: int,
    total_differences: int,
    two_teams: bool,
    snapshots: dict[str, SubmissionSnapshot],
) -> dict[str, DiffOutcome]:
    """Score one round: apply the correctness gate, then fewest-characters-wins.

    Returns one ``DiffOutcome`` per team. The winner (two-team mode only) is
    the eligible team with the fewest characters; ties make every tied team a
    winner.
    """
    eligible = {team_id: snap for team_id, snap in snapshots.items() if _is_eligible(snapshot=snap)}
    winners: set[str] = set()
    if eligible:
        min_characters = min(snap.characters for snap in eligible.values())
        winners = {
            team_id for team_id, snap in eligible.items() if snap.characters == min_characters
        }
    team_ids = list(snapshots.keys())
    outcomes: dict[str, DiffOutcome] = {}
    for team_id, snap in snapshots.items():
        opponent_snapshot: SubmissionSnapshot | None = None
        if two_teams:
            opponent_ids = [other for other in team_ids if other != team_id]
            if opponent_ids:
                opponent_snapshot = snapshots[opponent_ids[0]]
        outcomes[team_id] = DiffOutcome(
            case_number=case_number,
            team_id=team_id,
            total_differences=total_differences,
            found_count=snap.found_count,
            false_positive_count=snap.false_positive_count,
            found_all=snap.found_all,
            submitted=snap.submitted,
            characters_used=snap.characters,
            eligible=_is_eligible(snapshot=snap),
            won=(two_teams and team_id in winners),
            competitive=two_teams,
            opponent_found_all=(opponent_snapshot.found_all if opponent_snapshot else None),
            opponent_eligible=(
                _is_eligible(snapshot=opponent_snapshot) if opponent_snapshot else None
            ),
            opponent_characters=(opponent_snapshot.characters if opponent_snapshot else None),
        )
    return outcomes
