"""Evaluator that counts how many Veyru entities were stabilized.

A round is won when a team's field observer calls ``stabilize_veyru`` with
an action that the LLM judge approves before the communication budget runs
out and the Veyru collapses. In two-team mode, each (team, round) counts
as a separate opportunity and success is reported per team.
"""

import logging
from pathlib import Path

from schmidt.evaluation.evaluation_report import MetricResult
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.round_success_core import (
    TEAM_A_AGENT_IDS,
    TEAM_B_AGENT_IDS,
    compute_team_result,
    count_total_rounds,
    filter_events_for_team,
    is_two_team_mode,
    score_to_verdict,
)
from schmidt.scenarios.veyru.ids import LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID, TEAM_SOLO_ID

logger = logging.getLogger(__name__)


class RoundSuccessEvaluator(Evaluator):
    """Counts rounds where a Veyru was stabilized before collapse.

    Produces a score equal to the fraction of (team, round) pairs won.
    Does not require an LLM — results are determined from tool results
    and world events.
    """

    name = "round_success"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Count successful stabilizations from tool results and world events."""
        _ = scenario, llm_provider, run_dir
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
            joint_won_rounds = sorted(set(team_a_result.won_rounds) & set(team_b_result.won_rounds))
            joint_won = len(joint_won_rounds)
            if total_rounds > 0:
                score = joint_won / total_rounds
            else:
                score = 0.0
            verdict = score_to_verdict(score=score)
            evidence = [
                f"{joint_won}/{total_rounds} rounds stabilized by BOTH teams (a round "
                "counts only when Team A and Team B both succeed).",
                f"Team A: {team_a_result.won}/{total_rounds} stabilized.",
                f"Team B: {team_b_result.won}/{total_rounds} stabilized.",
            ]
            if team_a_result.lost_details:
                evidence.append("Team A losses: " + "; ".join(team_a_result.lost_details[:10]))
            if team_b_result.lost_details:
                evidence.append("Team B losses: " + "; ".join(team_b_result.lost_details[:10]))
            return MetricResult(
                evaluator_name=self.name,
                verdict=verdict,
                score=score,
                evidence=evidence,
                per_agent={},
                rounds_identified=joint_won_rounds,
            )

        solo_result = compute_team_result(
            round_numbers=round_numbers,
            events=events,
            label=TEAM_SOLO_ID,
        )
        if total_rounds > 0:
            score = solo_result.won / total_rounds
        else:
            score = 0.0
        verdict = score_to_verdict(score=score)
        evidence = [f"{solo_result.won}/{total_rounds} Veyru entities stabilized"]
        if solo_result.lost_details:
            evidence.append("Lost rounds: " + "; ".join(solo_result.lost_details[:10]))
        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
            rounds_identified=solo_result.won_rounds,
        )
