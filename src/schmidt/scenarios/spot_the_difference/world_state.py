"""Mutable per-team state, immutable outcome types, and round scoring.

The world holds one ``TeamState`` per team (solo mode keeps one; two-team
mode keeps two). Each ``TeamState`` carries the running link-channel character
count, the team's per-member submissions, the locked team verdict, and the
rolling list of finished ``DiffOutcome`` entries. ``build_round_outcomes`` is
the single place the correctness gate and the fewest-characters-wins comparison
live, shared by the live world and the event-log reconstructor.

When ``all_must_submit`` is set, a team is "complete" only once every member
has submitted; the team verdict then requires both answers to agree on the same
full set of differences (see :mod:`difference_judge.combine_team_verdict`).
"""

from dataclasses import dataclass, field
from typing import NamedTuple


class DiffOutcome(NamedTuple):
    """Result of one round for one team.

    ``eligible`` is the gate (the submission requirement met, every planted
    difference found, no false positives, and the character budget not
    exceeded). ``won`` is True only in two-team mode for the eligible team(s)
    with the fewest characters. ``members_submitted`` / ``members_required``
    record the submission gate (``members_required`` is 2 under
    ``all_must_submit``, else 1) and ``agreed`` is whether the members' answers
    matched the same set of differences. The ``opponent_*`` fields describe the
    single other team in two-team mode and are ``None`` in solo mode.
    """

    case_number: int
    team_id: str
    total_differences: int
    found_count: int
    false_positive_count: int
    found_all: bool
    submitted: bool
    budget_exceeded: bool
    characters_used: int
    members_submitted: int
    members_required: int
    agreed: bool
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
    budget_exceeded: bool
    characters: int
    members_submitted: int
    members_required: int
    agreed: bool


@dataclass
class TeamState:
    """All per-team mutable state the world tracks for one team."""

    team_id: str
    link_channel_id: str
    member_agent_ids: frozenset[str]
    all_must_submit: bool
    current_round_characters: int = 0
    round_budget_exceeded: bool = False
    submissions_by_agent: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    team_locked: bool = False
    verdict_recorded: bool = False
    team_found_all: bool = False
    team_false_positives: int = 0
    team_found_count: int = 0
    team_agreed: bool = True
    characters_at_submission: int = 0
    round_outcome_marked: bool = False
    notified_thresholds: set[str] = field(default_factory=set[str])
    outcomes: list[DiffOutcome] = field(default_factory=list[DiffOutcome])

    @property
    def members_required(self) -> int:
        """How many members must submit for the team to be scored."""
        if self.all_must_submit:
            return len(self.member_agent_ids)
        return 1

    @property
    def is_complete(self) -> bool:
        """Whether the team has met its submission requirement this round."""
        return len(self.submissions_by_agent) >= self.members_required

    def has_agent_submitted(self, agent_id: str) -> bool:
        """Whether ``agent_id`` has already submitted this round."""
        return agent_id in self.submissions_by_agent

    def snapshot(self) -> SubmissionSnapshot:
        """Capture this team's end-of-round submission state."""
        if self.team_locked:
            characters = self.characters_at_submission
        else:
            characters = self.current_round_characters
        return SubmissionSnapshot(
            submitted=self.team_locked,
            found_all=self.team_found_all,
            false_positive_count=self.team_false_positives,
            found_count=self.team_found_count,
            budget_exceeded=self.round_budget_exceeded,
            characters=characters,
            members_submitted=len(self.submissions_by_agent),
            members_required=self.members_required,
            agreed=self.team_agreed,
        )

    def reset_for_new_round(self) -> None:
        """Clear all per-round counters, submissions, and the locked verdict."""
        self.current_round_characters = 0
        self.round_budget_exceeded = False
        self.submissions_by_agent = {}
        self.team_locked = False
        self.verdict_recorded = False
        self.team_found_all = False
        self.team_false_positives = 0
        self.team_found_count = 0
        self.team_agreed = True
        self.characters_at_submission = 0
        self.round_outcome_marked = False
        self.notified_thresholds = set()


def _is_eligible(snapshot: SubmissionSnapshot) -> bool:
    """Whether a snapshot passes the gate: complete, correct, no false positives, within budget."""
    return (
        snapshot.submitted
        and snapshot.found_all
        and snapshot.false_positive_count == 0
        and not snapshot.budget_exceeded
    )


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
            budget_exceeded=snap.budget_exceeded,
            characters_used=snap.characters,
            members_submitted=snap.members_submitted,
            members_required=snap.members_required,
            agreed=snap.agreed,
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
