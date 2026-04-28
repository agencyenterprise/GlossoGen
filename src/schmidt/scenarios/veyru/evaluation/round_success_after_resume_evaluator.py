"""Round-success score restricted to the rounds played after a replace-agent swap.

Mirrors ``RoundSuccessEvaluator`` but filters the scored round set to
``[round_start, round_start + rounds_after_swap]`` as recorded in the
run's ``replace_manifest.json``. Runs without a manifest are not
applicable: the evaluator emits a ``FAIL`` verdict with an explanatory
evidence string (matching the convention used by
``ProtocolLearnedAfterSwapEvaluator``).
"""

import logging
from pathlib import Path

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.replace_manifest import ReplaceManifest, read_replace_manifest
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.round_success_core import (
    TEAM_A_AGENT_IDS,
    TEAM_B_AGENT_IDS,
    collect_advanced_round_numbers,
    compute_team_result,
    filter_events_for_team,
    is_two_team_mode,
    score_to_verdict,
)
from schmidt.scenarios.veyru.ids import LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID, TEAM_SOLO_ID

logger = logging.getLogger(__name__)


class RoundSuccessAfterResumeEvaluator(Evaluator):
    """Counts post-resume rounds where a Veyru was stabilized before collapse.

    Same accounting as ``RoundSuccessEvaluator``, restricted to the rounds
    that actually played after the replace-agent swap. Pre-resume rounds
    (copied from the source run) are excluded from both numerator and
    denominator.
    """

    name = "round_success_after_resume"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Score post-swap rounds, or report N/A on non-resume runs."""
        _ = scenario, llm_provider
        manifest = read_replace_manifest(run_dir=run_dir)
        if manifest is None:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    "Run is not a replace-agent run; round_success_after_resume does not apply."
                ],
                per_agent={},
                rounds_identified=[],
            )

        scored_rounds = _resolve_scored_rounds(events=events, manifest=manifest)
        total = len(scored_rounds)
        if total == 0:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    "Replace-agent run did not advance any post-resume round "
                    f"(round_start={manifest.round_start}, "
                    f"rounds_after_swap={manifest.rounds_after_swap})."
                ],
                per_agent={},
                rounds_identified=[],
            )

        is_two_team = is_two_team_mode(agent_configs=agent_configs)
        if is_two_team:
            return _evaluate_two_team(
                events=events,
                scored_rounds=scored_rounds,
                evaluator_name=self.name,
                manifest=manifest,
            )
        return _evaluate_single_team(
            events=events,
            scored_rounds=scored_rounds,
            evaluator_name=self.name,
            manifest=manifest,
        )


def _resolve_scored_rounds(
    events: list[SimulationEvent],
    manifest: ReplaceManifest,
) -> list[int]:
    """Return rounds in ``[round_start, round_start + rounds_after_swap]`` that advanced."""
    candidate = set(
        range(manifest.round_start, manifest.round_start + manifest.rounds_after_swap + 1)
    )
    advanced = collect_advanced_round_numbers(events=events)
    return sorted(candidate & advanced)


def _evaluate_single_team(
    events: list[SimulationEvent],
    scored_rounds: list[int],
    evaluator_name: str,
    manifest: ReplaceManifest,
) -> MetricResult:
    """Score a single-team Veyru run over ``scored_rounds`` only."""
    solo_result = compute_team_result(
        round_numbers=scored_rounds,
        events=events,
        label=TEAM_SOLO_ID,
    )
    total = len(scored_rounds)
    score = solo_result.won / total
    verdict = score_to_verdict(score=score)
    evidence = [
        f"{solo_result.won}/{total} Veyru entities stabilized in post-resume rounds "
        f"(round_start={manifest.round_start}, rounds_after_swap={manifest.rounds_after_swap}).",
        f"Scored rounds: {scored_rounds}.",
    ]
    if solo_result.lost_details:
        evidence.append("Lost rounds: " + "; ".join(solo_result.lost_details[:10]))
    return MetricResult(
        evaluator_name=evaluator_name,
        verdict=verdict,
        score=score,
        evidence=evidence,
        per_agent={},
        rounds_identified=solo_result.won_rounds,
    )


def _evaluate_two_team(
    events: list[SimulationEvent],
    scored_rounds: list[int],
    evaluator_name: str,
    manifest: ReplaceManifest,
) -> MetricResult:
    """Score a two-team Veyru run; a round counts only if both teams stabilize."""
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
        round_numbers=scored_rounds,
        events=team_a_events,
        label="Team A",
    )
    team_b_result = compute_team_result(
        round_numbers=scored_rounds,
        events=team_b_events,
        label="Team B",
    )
    joint_won_rounds = sorted(set(team_a_result.won_rounds) & set(team_b_result.won_rounds))
    joint_won = len(joint_won_rounds)
    total = len(scored_rounds)
    score = joint_won / total
    verdict = score_to_verdict(score=score)
    evidence = [
        f"{joint_won}/{total} post-resume rounds stabilized by BOTH teams "
        f"(round_start={manifest.round_start}, rounds_after_swap={manifest.rounds_after_swap}).",
        f"Team A: {team_a_result.won}/{total} stabilized.",
        f"Team B: {team_b_result.won}/{total} stabilized.",
        f"Scored rounds: {scored_rounds}.",
    ]
    if team_a_result.lost_details:
        evidence.append("Team A losses: " + "; ".join(team_a_result.lost_details[:10]))
    if team_b_result.lost_details:
        evidence.append("Team B losses: " + "; ".join(team_b_result.lost_details[:10]))
    return MetricResult(
        evaluator_name=evaluator_name,
        verdict=verdict,
        score=score,
        evidence=evidence,
        per_agent={},
        rounds_identified=joint_won_rounds,
    )
