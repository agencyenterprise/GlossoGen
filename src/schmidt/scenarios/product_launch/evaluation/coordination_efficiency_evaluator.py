"""Automated evaluator measuring coordination efficiency across the simulation.

Computes dependency lag (how many rounds pass between a backend feature reaching
70% and the first frontend effort allocation), wasted effort (effort spent on
features whose dependencies are unmet), resource reallocation speed (how quickly
agents shift priorities after budget pressure), and effort distribution entropy.
"""

import logging
import math
from typing import Any

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import GroundTruthSnapshot, SimulationEvent, ToolCalled, TurnAssigned
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

BACKEND_READY_THRESHOLD = 0.70


class CoordinationEfficiencyEvaluator(Evaluator):
    """Measures how effectively agents coordinate dependency handoffs and resources.

    All metrics are computed deterministically from the event log.
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,  # noqa: ARG002
        llm_provider: LLMProvider,  # noqa: ARG002
    ) -> MetricResult:
        """Compute coordination efficiency metrics from ground truth and effort events."""
        logger.info("CoordinationEfficiencyEvaluator: analyzing event log")

        ground_truth_by_round = _extract_ground_truth_by_round(events=events)
        effort_allocations = _extract_effort_allocations(events=events)

        dep_lag_result = _compute_dependency_lag(
            ground_truth_by_round=ground_truth_by_round,
            effort_allocations=effort_allocations,
        )

        wasted = _compute_wasted_effort(
            ground_truth_by_round=ground_truth_by_round,
            effort_allocations=effort_allocations,
        )

        realloc_speed = _compute_reallocation_speed(
            ground_truth_by_round=ground_truth_by_round,
            effort_allocations=effort_allocations,
        )

        entropy = _compute_effort_entropy(
            effort_allocations=effort_allocations,
        )

        dep_lag = dep_lag_result[0]
        evidence: list[str] = []
        evidence.append(f"Mean dependency lag: {dep_lag:.1f} rounds")
        evidence.append(f"Wasted effort (deps unmet): {wasted:.0f} RU")
        evidence.append(f"Reallocation speed: {realloc_speed}")
        evidence.append(f"Effort distribution entropy: {entropy:.2f}")

        for detail in dep_lag_result[1]:
            evidence.append(f"  {detail}")

        score = 1.0
        if dep_lag > 2.0:
            score -= 0.2
        elif dep_lag > 1.0:
            score -= 0.1
        score -= min(0.3, wasted / 200.0)
        if realloc_speed == "slow":
            score -= 0.2
        elif realloc_speed == "moderate":
            score -= 0.1
        if entropy < 1.0:
            score -= 0.1
        score = max(0.0, min(1.0, score))

        if score >= 0.7:
            verdict = Verdict.PASS
        elif score >= 0.4:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.FAIL

        per_agent: dict[str, Verdict] = {}
        agent_waste = _compute_per_agent_waste(
            ground_truth_by_round=ground_truth_by_round,
            effort_allocations=effort_allocations,
        )
        for ac in agent_configs:
            w = agent_waste.get(ac.agent_id, 0.0)
            if w < 10.0:
                per_agent[ac.agent_id] = Verdict.PASS
            elif w < 30.0:
                per_agent[ac.agent_id] = Verdict.PARTIAL
            else:
                per_agent[ac.agent_id] = Verdict.FAIL

        return MetricResult(
            evaluator_name="coordination_efficiency",
            verdict=verdict,
            score=round(score, 3),
            evidence=evidence,
            per_agent=per_agent,
        )


def _extract_ground_truth_by_round(
    events: list[SimulationEvent],
) -> dict[int, dict[str, Any]]:
    """Build a map of round_number -> ground truth state."""
    result: dict[int, dict[str, Any]] = {}
    for event in events:
        if isinstance(event, GroundTruthSnapshot):
            result[event.round_number] = event.state
    return result


def _extract_effort_allocations(
    events: list[SimulationEvent],
) -> list[dict[str, Any]]:
    """Extract allocate_effort tool calls with round context from TurnAssigned."""
    current_round = 0
    allocations: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event, TurnAssigned):
            current_round = event.round_number
        elif isinstance(event, ToolCalled) and event.request.tool_name == "allocate_effort":
            allocations.append(
                {
                    "agent_id": event.agent_id,
                    "round": current_round,
                    "feature_id": event.request.arguments.get("feature_id", ""),
                    "level": event.request.arguments.get("level", "standard"),
                }
            )
    return allocations


def _get_feature_dependencies(
    ground_truth_by_round: dict[int, dict[str, Any]],
) -> dict[str, list[str]]:
    """Get feature dependency map from the first ground truth snapshot."""
    for _rnd in sorted(ground_truth_by_round.keys()):
        state = ground_truth_by_round[_rnd]
        features = state.get("features", [])
        return {f["feature_id"]: f.get("integration_dependencies", []) for f in features}
    return {}


def _compute_dependency_lag(
    ground_truth_by_round: dict[int, dict[str, Any]],
    effort_allocations: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    """Compute mean rounds between backend reaching 70% and first frontend effort.

    For features with dependencies, measures when the dependency's backend
    reaches 70% versus when any agent starts effort on the dependent feature.
    Returns (mean_lag, detail_strings).
    """
    details: list[str] = []
    deps = _get_feature_dependencies(ground_truth_by_round=ground_truth_by_round)

    backend_ready_round: dict[str, int] = {}
    for rnd in sorted(ground_truth_by_round.keys()):
        features = ground_truth_by_round[rnd].get("features", [])
        for f in features:
            fid = f["feature_id"]
            if fid not in backend_ready_round:
                if f.get("backend_completion_pct", 0.0) >= BACKEND_READY_THRESHOLD:
                    backend_ready_round[fid] = rnd

    first_effort_round: dict[str, int] = {}
    for alloc in effort_allocations:
        fid = alloc["feature_id"]
        if fid not in first_effort_round:
            first_effort_round[fid] = alloc["round"]
        elif alloc["round"] < first_effort_round[fid]:
            first_effort_round[fid] = alloc["round"]

    lags: list[float] = []
    for fid, dep_list in deps.items():
        for dep_fid in dep_list:
            ready_round = backend_ready_round.get(dep_fid)
            effort_round = first_effort_round.get(fid)
            if ready_round is not None and effort_round is not None:
                lag = max(0, effort_round - ready_round)
                lags.append(float(lag))
                details.append(
                    f"{fid} depends on {dep_fid}: "
                    f"dep backend ready round {ready_round}, "
                    f"first effort round {effort_round}, lag={lag}"
                )

    if not lags:
        return (0.0, details)
    return (sum(lags) / len(lags), details)


def _compute_wasted_effort(
    ground_truth_by_round: dict[int, dict[str, Any]],
    effort_allocations: list[dict[str, Any]],
) -> float:
    """Sum of effort RU spent on features whose dependencies are not yet met.

    'Met' means the dependency feature has reached integration_ready or beyond.
    """
    deps = _get_feature_dependencies(ground_truth_by_round=ground_truth_by_round)

    level_to_ru = {"reduced": 5.0, "standard": 10.0, "accelerated": 20.0}

    wasted = 0.0
    for alloc in effort_allocations:
        fid = alloc["feature_id"]
        rnd = alloc["round"]
        feature_deps = deps.get(fid, [])
        if not feature_deps:
            continue

        gt = ground_truth_by_round.get(rnd)
        if gt is None:
            continue

        features_by_id = {f["feature_id"]: f for f in gt.get("features", [])}
        deps_met = True
        ready_statuses = {
            "integration_ready",
            "qa_testing",
            "qa_passed",
            "shipped",
        }
        for dep_fid in feature_deps:
            dep_feature = features_by_id.get(dep_fid)
            if dep_feature is None or dep_feature.get("status") not in ready_statuses:
                deps_met = False
                break

        if not deps_met:
            wasted += level_to_ru.get(alloc["level"], 10.0)

    return wasted


def _compute_per_agent_waste(
    ground_truth_by_round: dict[int, dict[str, Any]],
    effort_allocations: list[dict[str, Any]],
) -> dict[str, float]:
    """Wasted effort broken down by agent."""
    deps = _get_feature_dependencies(ground_truth_by_round=ground_truth_by_round)
    level_to_ru = {"reduced": 5.0, "standard": 10.0, "accelerated": 20.0}
    ready_statuses = {"integration_ready", "qa_testing", "qa_passed", "shipped"}

    waste_by_agent: dict[str, float] = {}
    for alloc in effort_allocations:
        fid = alloc["feature_id"]
        rnd = alloc["round"]
        feature_deps = deps.get(fid, [])
        if not feature_deps:
            continue

        gt = ground_truth_by_round.get(rnd)
        if gt is None:
            continue

        features_by_id = {f["feature_id"]: f for f in gt.get("features", [])}
        deps_met = True
        for dep_fid in feature_deps:
            dep_feature = features_by_id.get(dep_fid)
            if dep_feature is None or dep_feature.get("status") not in ready_statuses:
                deps_met = False
                break

        if not deps_met:
            aid = alloc["agent_id"]
            waste_by_agent[aid] = waste_by_agent.get(aid, 0.0) + level_to_ru.get(
                alloc["level"], 10.0
            )

    return waste_by_agent


def _compute_reallocation_speed(
    ground_truth_by_round: dict[int, dict[str, Any]],
    effort_allocations: list[dict[str, Any]],
) -> str:
    """Classify how quickly agents shift priorities after budget pressure appears.

    Budget pressure is defined as the round where >50% of budget is spent.
    Speed is judged by how much the effort allocation pattern changes after
    that round (measured by feature distribution shift).
    """
    pressure_round = _find_budget_pressure_round(
        ground_truth_by_round=ground_truth_by_round,
    )
    if pressure_round is None:
        return "no_pressure"

    before: dict[str, int] = {}
    after: dict[str, int] = {}
    for alloc in effort_allocations:
        fid = alloc["feature_id"]
        if alloc["round"] <= pressure_round:
            before[fid] = before.get(fid, 0) + 1
        else:
            after[fid] = after.get(fid, 0) + 1

    if not before or not after:
        return "insufficient_data"

    all_features = set(before.keys()) | set(after.keys())
    before_total = sum(before.values())
    after_total = sum(after.values())
    if before_total == 0 or after_total == 0:
        return "insufficient_data"

    shift = 0.0
    for fid in all_features:
        b_frac = before.get(fid, 0) / before_total
        a_frac = after.get(fid, 0) / after_total
        shift += abs(a_frac - b_frac)
    shift /= 2.0

    if shift > 0.3:
        return "fast"
    elif shift > 0.15:
        return "moderate"
    else:
        return "slow"


def _find_budget_pressure_round(
    ground_truth_by_round: dict[int, dict[str, Any]],
) -> int | None:
    """Find the first round where >50% of total budget has been spent."""
    for rnd in sorted(ground_truth_by_round.keys()):
        budget = ground_truth_by_round[rnd].get("budget", {})
        total = budget.get("total_budget_ru", 0)
        spent = budget.get("spent_ru", 0)
        if total > 0 and spent > total * 0.5:
            return rnd
    return None


def _compute_effort_entropy(
    effort_allocations: list[dict[str, Any]],
) -> float:
    """Compute Shannon entropy of effort distribution across features.

    Higher entropy means more even distribution; lower means siloed.
    """
    feature_counts: dict[str, int] = {}
    for alloc in effort_allocations:
        fid = alloc["feature_id"]
        feature_counts[fid] = feature_counts.get(fid, 0) + 1

    total = sum(feature_counts.values())
    if total == 0:
        return 0.0

    entropy = 0.0
    for count in feature_counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy
