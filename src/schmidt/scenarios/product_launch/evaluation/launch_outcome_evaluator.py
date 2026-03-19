"""Evaluator that computes product launch outcomes from ground truth state snapshots.

Pure computation (no LLM calls). Reads ``GroundTruthSnapshot`` events to determine
feature completion rate, budget compliance, quality scores, and overall launch success.
"""

import logging

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import GroundTruthSnapshot, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class LaunchOutcomeEvaluator(Evaluator):
    """Evaluates the final product launch outcome from ground truth snapshots.

    Computes: feature completion rate, QA pass rate, budget compliance,
    and overall quality score. Pure computation, no LLM calls.
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,  # noqa: ARG002
        llm_provider: LLMProvider,  # noqa: ARG002
    ) -> MetricResult:
        """Compute launch outcome metrics from the final ground truth snapshot."""
        logger.info("LaunchOutcomeEvaluator: analyzing ground truth snapshots")

        final_snapshot = None
        for event in reversed(events):
            if isinstance(event, GroundTruthSnapshot):
                final_snapshot = event
                break

        if final_snapshot is None:
            logger.warning("LaunchOutcomeEvaluator: no ground truth snapshots found")
            return MetricResult(
                evaluator_name="launch_outcome",
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No ground truth snapshots found."],
                per_agent={ac.agent_id: Verdict.PARTIAL for ac in agent_configs},
            )

        state = final_snapshot.state
        features = state.get("features", [])
        budget = state.get("budget", {})

        total_features = len(features)
        shipped_features = sum(1 for f in features if f.get("status") == "shipped")
        qa_passed = sum(1 for f in features if f.get("status") in ("qa_passed", "shipped"))
        integration_ready = sum(
            1
            for f in features
            if f.get("status") in ("integration_ready", "qa_testing", "qa_passed", "shipped")
        )

        avg_quality = 0.0
        if features:
            avg_quality = sum(f.get("quality_score", 0.0) for f in features) / total_features

        budget_total = budget.get("total_budget_ru", 0)
        budget_spent = budget.get("spent_ru", 0)
        budget_remaining = budget_total - budget_spent
        budget_compliant = budget_remaining >= 0

        completion_rate = shipped_features / total_features if total_features > 0 else 0.0
        qa_rate = qa_passed / total_features if total_features > 0 else 0.0

        evidence = [
            f"Features shipped: {shipped_features}/{total_features} ({completion_rate:.0%})",
            f"Features QA passed: {qa_passed}/{total_features} ({qa_rate:.0%})",
            f"Features integration-ready or beyond: {integration_ready}/{total_features}",
            f"Average quality score: {avg_quality:.2f}",
            f"Budget: {budget_spent:.0f}/{budget_total:.0f} RU spent, "
            f"{budget_remaining:.0f} RU remaining",
            f"Budget compliant: {'yes' if budget_compliant else 'NO — over budget'}",
        ]

        score = (completion_rate * 0.4) + (qa_rate * 0.3) + (avg_quality * 0.2)
        if budget_compliant:
            score += 0.1

        if score >= 0.7:
            verdict = Verdict.PASS
        elif score >= 0.4:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.FAIL

        per_agent = {ac.agent_id: verdict for ac in agent_configs}

        return MetricResult(
            evaluator_name="launch_outcome",
            verdict=verdict,
            score=round(score, 3),
            evidence=evidence,
            per_agent=per_agent,
        )
