"""Rebuilding veyru outcomes from an event log decides stabilization per team."""

from glossogen.engine.round_outcome_log import RoundOutcomeLog
from glossogen.models.event import RoundEnded
from glossogen.scenarios.veyru.events import VeyruStabilizationJudged
from glossogen.scenarios.veyru.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_B_ID,
    TEAM_A_ID,
    TEAM_B_ID,
    TeamId,
)
from glossogen.scenarios.veyru.outcome_reconstruction import restore_outcomes_from_events
from glossogen.scenarios.veyru.veyru_cases import VeyruCase, get_cases
from glossogen.scenarios.veyru.world_state import TeamState, VeyruOutcome


def _two_teams() -> dict[TeamId, TeamState]:
    return {
        TEAM_A_ID: TeamState(
            team_id=TEAM_A_ID,
            current_observer_id=OBSERVER_A_ID,
            stabilization_engineer_id=STABILIZATION_ENGINEER_A_ID,
            link_channel_id=LINK_A_CHANNEL_ID,
            postmortem_channel_id=None,
        ),
        TEAM_B_ID: TeamState(
            team_id=TEAM_B_ID,
            current_observer_id=OBSERVER_B_ID,
            stabilization_engineer_id=STABILIZATION_ENGINEER_B_ID,
            link_channel_id=LINK_B_CHANNEL_ID,
            postmortem_channel_id=None,
        ),
    }


def _judged(agent_id: str, case: VeyruCase, matched_stages: int) -> list[VeyruStabilizationJudged]:
    return [
        VeyruStabilizationJudged(
            round_number=1,
            agent_id=agent_id,
            expected_actions=stage.judge_expected_actions,
            judge_match=True,
            judge_explanation="matched",
        )
        for stage in case.stages[:matched_stages]
    ]


def test_a_mixed_outcome_round_records_the_stabilized_team_as_stabilized() -> None:
    """Team A matched every stage and team B none, so the round ended split."""
    cases = get_cases(
        seed=42, round_count=1, round_time_budget_seconds=800, easy_round_numbers=frozenset()
    )
    case = cases[0]
    teams = _two_teams()
    outcome_log: RoundOutcomeLog[VeyruOutcome] = RoundOutcomeLog(team_ids=tuple(teams))
    events = [
        *_judged(agent_id=STABILIZATION_ENGINEER_A_ID, case=case, matched_stages=len(case.stages)),
        RoundEnded(round_number=1, trigger="veyru_mixed_outcome"),
    ]

    restore_outcomes_from_events(
        teams=teams, veyru_cases=cases, events=events, outcome_log=outcome_log
    )

    team_a = outcome_log.recorded_for(team_id=TEAM_A_ID, round_number=1)
    team_b = outcome_log.recorded_for(team_id=TEAM_B_ID, round_number=1)
    assert team_a is not None and team_a.stabilized
    assert team_a.stages_completed == len(case.stages)
    assert team_b is not None and not team_b.stabilized
    assert team_b.stages_completed == 0


def test_a_team_short_of_the_last_stage_is_not_stabilized() -> None:
    """A round that ended on every team stabilizing still reads the judged stages."""
    cases = get_cases(
        seed=42, round_count=1, round_time_budget_seconds=800, easy_round_numbers=frozenset()
    )
    case = cases[0]
    teams = _two_teams()
    outcome_log: RoundOutcomeLog[VeyruOutcome] = RoundOutcomeLog(team_ids=tuple(teams))
    events = [
        *_judged(
            agent_id=STABILIZATION_ENGINEER_B_ID, case=case, matched_stages=len(case.stages) - 1
        ),
        RoundEnded(round_number=1, trigger="veyru_stabilized"),
    ]

    restore_outcomes_from_events(
        teams=teams, veyru_cases=cases, events=events, outcome_log=outcome_log
    )

    team_b = outcome_log.recorded_for(team_id=TEAM_B_ID, round_number=1)
    assert team_b is not None and not team_b.stabilized
    assert team_b.stages_completed == len(case.stages) - 1
