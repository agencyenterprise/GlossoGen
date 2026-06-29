"""World simulation for the spot_the_difference scenario.

Tracks per-team link-channel character usage and the team's locked
submission. The world is mutated by the one scenario tool: a viewer calls
``submit_differences`` with a free-text list of differences; the tool locks
the team's answer (snapshotting its character count), the LLM judge scores it,
and ``record_submission_result`` stores the verdict. At round end the world
scores every team — correctness gate, then fewest-characters-wins — and
reveals each team's result on its link channel.

Heavy logic lives in dedicated sibling modules: :mod:`world_state` (the
``TeamState`` / ``DiffOutcome`` types and the round-scoring function) and
:mod:`outcome_reconstruction` (rebuilding outcomes from a JSONL event log on
resume).
"""

import asyncio
import logging
from typing import Any

from schmidt.runtime.scenario_world import RoundAdvancedEvent, ScenarioWorld, WorldContext
from schmidt.scenarios.spot_the_difference.ids import (
    BUDGET_EXCEEDED_MARKER,
    BUDGET_LOW_MARKER,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    ROUND_LOST_MARKER,
    ROUND_RESULT_MARKER,
    ROUND_WON_MARKER,
    SUBMISSION_RECORDED_MARKER,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
)
from schmidt.scenarios.spot_the_difference.outcome_reconstruction import (
    restore_outcomes_from_events,
)
from schmidt.scenarios.spot_the_difference.scene_generation import DiffCase
from schmidt.scenarios.spot_the_difference.team_routing import team_id_for_channel
from schmidt.scenarios.spot_the_difference.world_state import (
    DiffOutcome,
    TeamState,
    build_round_outcomes,
)

logger = logging.getLogger(__name__)

_THRESHOLD_LOW = "low"
_THRESHOLD_EXCEEDED = "exceeded"


class SpotTheDifferenceWorld(ScenarioWorld):
    """Per-team world that accumulates link characters and locks submissions.

    Single-team mode holds one ``TeamState`` keyed by ``TEAM_SOLO_ID``;
    two-team mode holds two, keyed by ``TEAM_A_ID`` / ``TEAM_B_ID``.
    """

    _context: WorldContext

    def __init__(
        self,
        cases: list[DiffCase],
        postmortem_globally_disabled: bool,
        two_teams: bool,
    ) -> None:
        self._cases = cases
        self._two_teams = two_teams
        self._current_case: DiffCase | None = None
        self._in_postmortem: bool = False
        self._postmortem_globally_disabled: bool = postmortem_globally_disabled
        self._teams: dict[str, TeamState] = self._build_teams(two_teams=two_teams)

    @staticmethod
    def _build_teams(two_teams: bool) -> dict[str, TeamState]:
        """Initialize the team-state map for single or two-team mode."""
        if two_teams:
            return {
                TEAM_A_ID: TeamState(team_id=TEAM_A_ID, link_channel_id=LINK_A_CHANNEL_ID),
                TEAM_B_ID: TeamState(team_id=TEAM_B_ID, link_channel_id=LINK_B_CHANNEL_ID),
            }
        return {
            TEAM_SOLO_ID: TeamState(team_id=TEAM_SOLO_ID, link_channel_id=LINK_CHANNEL_ID),
        }

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def two_teams(self) -> bool:
        """Whether the world is running two parallel teams."""
        return self._two_teams

    @property
    def team_ids(self) -> list[str]:
        """Stable list of the team identifiers this world tracks."""
        return list(self._teams.keys())

    @property
    def current_case(self) -> DiffCase | None:
        """The difference case for the current round (shared across teams)."""
        return self._current_case

    @property
    def in_postmortem(self) -> bool:
        """Whether the simulation is in a postmortem discussion phase."""
        return self._in_postmortem

    @property
    def is_postmortem_disabled(self) -> bool:
        """Whether postmortem has been globally disabled."""
        return self._postmortem_globally_disabled

    def current_round_characters(self, team_id: str) -> int:
        """Running character count on ``team_id``'s link channel this round."""
        return self._teams[team_id].current_round_characters

    def all_teams_done(self) -> bool:
        """Whether every team is finished this round (verdict recorded or budget blown).

        Gated on the recorded verdict, not just the lock: ``try_lock_submission``
        sets ``submitted`` before the async judge runs, so ending the round on
        the lock alone would let the round be scored before the verdict lands. A
        team that exhausts its character budget is also done (and ineligible).
        """
        return all(
            team.verdict_recorded or team.round_budget_exceeded for team in self._teams.values()
        )

    def outcomes(self, team_id: str) -> list[DiffOutcome]:
        """Historical per-round outcomes for one team."""
        return self._teams[team_id].outcomes

    def previous_outcome(self, team_id: str) -> DiffOutcome | None:
        """Return ``team_id``'s most recent outcome, or None when no rounds finished."""
        outcomes = self._teams[team_id].outcomes
        if len(outcomes) == 0:
            return None
        return outcomes[-1]

    def enter_postmortem(self) -> None:
        """Mark the start of a postmortem discussion phase."""
        self._in_postmortem = True

    def exit_postmortem(self) -> None:
        """Mark the end of a postmortem discussion phase."""
        self._in_postmortem = False

    def disable_postmortem_globally(self) -> None:
        """Close the postmortem channel for the rest of the simulation."""
        self._postmortem_globally_disabled = True

    def get_globally_disabled_channels(self) -> frozenset[str]:
        """Postmortem channels when disabled (single-team and two-team variants)."""
        if not self._postmortem_globally_disabled:
            return frozenset()
        return frozenset({POSTMORTEM_CHANNEL_ID, POSTMORTEM_A_CHANNEL_ID, POSTMORTEM_B_CHANNEL_ID})

    def try_lock_submission(self, team_id: str) -> int | None:
        """Lock ``team_id``'s answer for the round, returning its character count.

        Returns ``None`` if the team has already submitted. Synchronous and
        atomic: snapshots the live character count before any judge call so
        post-submission chatter cannot change the scored total.
        """
        team = self._teams[team_id]
        if team.submitted:
            return None
        team.submitted = True
        team.characters_at_submission = team.current_round_characters
        return team.characters_at_submission

    def record_submission_result(
        self,
        team_id: str,
        found_all: bool,
        false_positive_count: int,
        found_count: int,
    ) -> None:
        """Store the judge's verdict on ``team_id``'s locked submission."""
        team = self._teams[team_id]
        team.submitted_found_all = found_all
        team.submitted_false_positives = false_positive_count
        team.submitted_found_count = found_count
        team.verdict_recorded = True

    async def announce_submission_locked(self, team_id: str) -> None:
        """Notify the team's link channel that its answer is locked."""
        team = self._teams[team_id]
        await self._context.send_update_to_channel(
            channel_id=team.link_channel_id,
            text=f"{SUBMISSION_RECORDED_MARKER}. Your team's answer is locked for this round.",
        )

    def restore_outcomes_from_events(self, events: list[Any]) -> None:
        """Seed each team's ``outcomes`` from a JSONL event list on resume."""
        restore_outcomes_from_events(
            teams=self._teams,
            cases=self._cases,
            two_teams=self._two_teams,
            events=events,
        )

    def mark_round_outcome(self, round_number: int) -> None:
        """Score the just-ended round and append each team's ``DiffOutcome``."""
        case = self._current_case
        if case is None:
            return
        if all(team.round_outcome_marked for team in self._teams.values()):
            return
        snapshots = {team_id: team.snapshot() for team_id, team in self._teams.items()}
        outcomes = build_round_outcomes(
            case_number=round_number,
            total_differences=case.difference_count,
            two_teams=self._two_teams,
            snapshots=snapshots,
        )
        for team_id, team in self._teams.items():
            if team.round_outcome_marked:
                continue
            team.outcomes.append(outcomes[team_id])
            team.round_outcome_marked = True

    def finalize_round_sync(self, round_number: int) -> None:
        """Score the previous round if needed, load the next case, reset state."""
        assert (
            1 <= round_number <= len(self._cases)
        ), f"round_number {round_number} out of range [1, {len(self._cases)}]"
        if round_number >= 2:
            self.mark_round_outcome(round_number=round_number - 1)
        self._current_case = self._cases[round_number - 1]
        for team in self._teams.values():
            team.reset_for_new_round()

    async def emit_round_terminal_notification(self) -> None:
        """Reveal each team's result on its link channel after the round ends."""
        for team in self._teams.values():
            if len(team.outcomes) == 0:
                continue
            await self._context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=_render_terminal_text(outcome=team.outcomes[-1]),
            )

    def on_message(
        self,
        agent_id: str,
        channel_id: str,
        text: str,
        token_count: int,
    ) -> None:
        """Accumulate link-channel characters and flag budget exhaustion per team."""
        _ = agent_id, token_count
        team_id = team_id_for_channel(channel_id=channel_id)
        if team_id is None:
            return
        team = self._teams.get(team_id)
        if team is None:
            return
        if team.submitted:
            # Answer already locked; post-submission chatter does not change the score.
            return
        team.current_round_characters += len(text)
        case = self._current_case
        if case is None:
            return
        if team.current_round_characters >= case.round_time_budget_seconds:
            team.round_budget_exceeded = True

    async def run(self, context: WorldContext) -> None:
        """Process messages and warn each team as it nears / exceeds its budget."""
        self._context = context
        try:
            while True:
                event = await context.next_event()
                if isinstance(event, RoundAdvancedEvent):
                    continue
                team_id = team_id_for_channel(channel_id=event.channel_id)
                if team_id is None:
                    continue
                await self._send_budget_notifications(team_id=team_id)
        except asyncio.CancelledError:
            return

    async def _send_budget_notifications(self, team_id: str) -> None:
        """Emit a one-time budget-low and budget-exceeded notice for a team."""
        case = self._current_case
        if case is None:
            return
        team = self._teams[team_id]
        budget = case.round_time_budget_seconds
        used = team.current_round_characters
        if team.round_budget_exceeded and _THRESHOLD_EXCEEDED not in team.notified_thresholds:
            team.notified_thresholds.update([_THRESHOLD_LOW, _THRESHOLD_EXCEEDED])
            await self._context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=(
                    f"{BUDGET_EXCEEDED_MARKER}. You have sent {used} characters; the budget was "
                    f"{budget}. This round can no longer be won — submit now if you can."
                ),
            )
            return
        if used >= budget * 0.75 and _THRESHOLD_LOW not in team.notified_thresholds:
            team.notified_thresholds.add(_THRESHOLD_LOW)
            await self._context.send_update_to_channel(
                channel_id=team.link_channel_id,
                text=f"{BUDGET_LOW_MARKER}. {budget - used} of {budget} budget characters remain.",
            )


def _render_terminal_text(outcome: DiffOutcome) -> str:
    """Build the end-of-round reveal message for one team's link channel."""
    found = f"found {outcome.found_count}/{outcome.total_differences} differences"
    if outcome.false_positive_count > 0:
        found = f"{found}, {outcome.false_positive_count} incorrect"
    characters = f"{outcome.characters_used} characters"
    if outcome.budget_exceeded:
        return (
            f"{ROUND_RESULT_MARKER}. Communication budget exceeded ({characters}) — "
            f"ineligible this round ({found})."
        )
    if not outcome.submitted:
        return (
            f"{ROUND_RESULT_MARKER}. Your team did not submit in time "
            f"({found} would have been judged from your last lock)."
        )
    if not outcome.competitive:
        if outcome.eligible:
            return f"{ROUND_RESULT_MARKER}. Correct — {found} using {characters}."
        return f"{ROUND_RESULT_MARKER}. Incomplete — {found} using {characters}."
    if outcome.won:
        return (
            f"{ROUND_WON_MARKER}. {found} using {characters} — "
            f"fewest among teams that found everything."
        )
    if outcome.eligible:
        return f"{ROUND_LOST_MARKER}. {found} using {characters}; the other team used fewer."
    return f"{ROUND_LOST_MARKER}. {found} using {characters} — not all differences found."
