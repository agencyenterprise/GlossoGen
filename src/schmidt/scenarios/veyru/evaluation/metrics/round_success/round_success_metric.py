"""Metric that counts how many Veyru entities were stabilized.

A round is won when a team's field observer calls ``stabilize_veyru`` with
an action that the LLM judge approves before the communication budget runs
out and the Veyru collapses. In two-team mode, the metric emits one
Measurement per team (``round_success_team_a``, ``round_success_team_b``)
so each team's per-round outcomes stay intact.
"""

import logging
from pathlib import Path

from schmidt.evaluation.metric_core.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.metrics.round_success.scoring import (
    TEAM_A_AGENT_IDS,
    TEAM_B_AGENT_IDS,
    TeamResult,
    compute_team_result,
    count_total_rounds,
    filter_events_for_team,
    is_two_team_mode,
)
from schmidt.scenarios.veyru.ids import LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID, TEAM_SOLO_ID

logger = logging.getLogger(__name__)


class RoundSuccessMetric(Metric):
    """Counts rounds where a Veyru was stabilized before collapse.

    Single-team runs return one Measurement with ``metric_name="round_success"``.
    Two-team runs return two Measurements with ``metric_name="round_success_team_a"``
    and ``metric_name="round_success_team_b"``.
    """

    name = "round_success"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Count successful stabilizations from tool results and world events."""
        _ = scenario, llm_provider, run_dir, options
        is_two_team = is_two_team_mode(agent_configs=agent_configs)
        total_rounds = count_total_rounds(events=events)
        round_numbers = list(range(1, total_rounds + 1))

        if is_two_team:
            team_a_events = filter_events_for_team(
                events=events,
                agent_ids=TEAM_A_AGENT_IDS,
                link_channel_id=LINK_A_CHANNEL_ID,
            )
            team_b_events = filter_events_for_team(
                events=events,
                agent_ids=TEAM_B_AGENT_IDS,
                link_channel_id=LINK_B_CHANNEL_ID,
            )
            team_a_result = compute_team_result(
                round_numbers=round_numbers,
                events=team_a_events,
                label="Team A",
            )
            team_b_result = compute_team_result(
                round_numbers=round_numbers,
                events=team_b_events,
                label="Team B",
            )
            return [
                _build_team_measurement(
                    metric_name="round_success_team_a",
                    team_label="team_a",
                    total_rounds=total_rounds,
                    team_result=team_a_result,
                ),
                _build_team_measurement(
                    metric_name="round_success_team_b",
                    team_label="team_b",
                    total_rounds=total_rounds,
                    team_result=team_b_result,
                ),
            ]

        solo_result = compute_team_result(
            round_numbers=round_numbers,
            events=events,
            label=TEAM_SOLO_ID,
        )
        return [
            _build_team_measurement(
                metric_name=self.name,
                team_label=TEAM_SOLO_ID,
                total_rounds=total_rounds,
                team_result=solo_result,
            )
        ]


def _build_team_measurement(
    metric_name: str,
    team_label: str,
    total_rounds: int,
    team_result: TeamResult,
) -> Measurement:
    """Convert a TeamResult into a Measurement."""
    if total_rounds > 0:
        score = team_result.won / total_rounds
    else:
        score = 0.0
    per_round = [
        RoundObservation(
            round_number=outcome.round_number,
            value=1.0 if outcome.won else 0.0,
            note=outcome.note,
        )
        for outcome in team_result.round_outcomes
    ]
    summary = f"{team_label} stabilized in {team_result.won}/{total_rounds} rounds"
    return Measurement(
        metric_name=metric_name,
        score=score,
        score_unit=f"fraction of rounds {team_label} stabilized ({team_result.won}/{total_rounds})",
        summary=summary,
        per_round=per_round,
        per_agent=[],
    )
