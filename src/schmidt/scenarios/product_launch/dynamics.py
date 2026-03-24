"""Simulation dynamics for the product launch scenario.

Computes feature progress from level-based effort allocation (reduced /
standard / accelerated), models quality as a function of effort vs complexity,
enforces integration dependency ordering, handles post-QA bug-fixing,
models burnout risk from sustained accelerated effort, and defines
external event logic.
"""

import logging
import random
from enum import Enum
from typing import Any, NamedTuple

from schmidt.scenarios.product_launch.budget_model import BudgetTracker
from schmidt.scenarios.product_launch.feature_model import Feature, FeatureStatus

logger = logging.getLogger(__name__)

FRONTEND_BACKEND_THRESHOLD = 0.70
BUG_BASE_PROBABILITY = 0.15

QA_ROLE_ID = "qa_lead"

ACCELERATED_QUALITY_PENALTY = 0.03

QUALITY_REPAIR_BY_LEVEL: dict[str, float] = {
    "reduced": 0.04,
    "standard": 0.08,
    "accelerated": 0.10,
}

BURNOUT_PROBABILITY = 0.12
BURNOUT_DELAY_MIN = 1
BURNOUT_DELAY_MAX = 2


class EffortLevel(str, Enum):
    """Effort allocation level chosen by an agent for a feature."""

    REDUCED = "reduced"
    STANDARD = "standard"
    ACCELERATED = "accelerated"


EFFORT_UNITS_BY_LEVEL: dict[EffortLevel, float] = {
    EffortLevel.REDUCED: 1.5,
    EffortLevel.STANDARD: 3.0,
    EffortLevel.ACCELERATED: 5.0,
}

EFFORT_TO_PROGRESS_BASE = 0.12
QUALITY_DECAY_FACTOR = 0.05


class BurnoutEvent(NamedTuple):
    """A pending burnout event that will reduce an agent's output in a future round."""

    agent_id: str
    trigger_round: int


def resolve_effort_allocations(
    allocations: dict[str, EffortLevel],
    features: list[Feature],
    budget: BudgetTracker,
    round_number: int,
    agent_id: str,
    is_burned_out: bool,
) -> list[str]:
    """Apply all effort allocations for a round and return result summaries.

    Each allocation maps ``feature_id -> EffortLevel``. The engine converts
    levels to effort units, applies progress to backend then frontend
    (respecting the 70% backend threshold), and records budget spend.
    When ``is_burned_out`` is True, all allocations are downgraded to
    reduced level (the person called in sick / is exhausted).
    """
    features_by_id = {f.feature_id: f for f in features}
    results: list[str] = []

    for feature_id, level in allocations.items():
        feature = features_by_id.get(feature_id)
        if feature is None:
            results.append(f"Feature '{feature_id}' not found — skipped.")
            continue

        effective_level = level
        if is_burned_out:
            effective_level = EffortLevel.REDUCED

        effort_units = EFFORT_UNITS_BY_LEVEL[effective_level]
        result = _apply_effort(
            feature=feature,
            effort_units=effort_units,
            level=effective_level,
            budget=budget,
            round_number=round_number,
            agent_id=agent_id,
        )
        results.append(result)

    return results


def roll_burnout(
    agent_id: str,
    current_round: int,
    num_rounds: int,
) -> BurnoutEvent | None:
    """Roll for burnout from accelerated effort. Returns a future burnout event or None."""
    if random.random() >= BURNOUT_PROBABILITY:
        return None
    delay = random.randint(BURNOUT_DELAY_MIN, BURNOUT_DELAY_MAX)
    trigger_round = current_round + delay
    if trigger_round > num_rounds:
        return None
    logger.info(
        "Agent %s rolled burnout at round %d, will trigger at round %d",
        agent_id,
        current_round,
        trigger_round,
    )
    return BurnoutEvent(agent_id=agent_id, trigger_round=trigger_round)


def _apply_effort(
    feature: Feature,
    effort_units: float,
    level: EffortLevel,
    budget: BudgetTracker,
    round_number: int,
    agent_id: str,
) -> str:
    """Apply effort units to a feature.

    Build phase: advances backend then frontend completion. Accelerated
    effort by non-QA roles incurs a small quality penalty.
    Bug-fix phase (qa_failed): effort repairs quality instead of advancing
    progress, with accelerated being less efficient than standard.
    """
    is_qa = agent_id == QA_ROLE_ID

    if feature.status == FeatureStatus.QA_FAILED:
        quality_gain = QUALITY_REPAIR_BY_LEVEL[level.value]
        feature.quality_score = min(1.0, feature.quality_score + quality_gain)

        budget.record_spend(
            round_number=round_number,
            amount=effort_units,
            category=f"{level.value}_bugfix",
        )

        if feature.quality_score >= 0.7 and feature.qa.bugs_found > feature.qa.bugs_fixed:
            feature.qa.bugs_fixed = feature.qa.bugs_found
            feature.qa.passed = True
            feature.status = FeatureStatus.QA_PASSED

        update_feature_status(feature=feature)
        return (
            f"{feature.name}: {level.value} priority set for bug-fixing this week. "
            f"Quality score now {feature.quality_score:.2f}."
        )

    remaining = effort_units

    if feature.backend_completion_pct < 1.0:
        be_increment = _progress_increment(
            effort_units=remaining, complexity=feature.backend_complexity
        )
        feature.backend_completion_pct = min(1.0, feature.backend_completion_pct + be_increment)
        remaining = max(0.0, remaining - (be_increment * feature.backend_complexity))
    elif feature.backend_completion_pct >= FRONTEND_BACKEND_THRESHOLD:
        if feature.frontend_completion_pct < 1.0:
            fe_increment = _progress_increment(
                effort_units=remaining, complexity=feature.frontend_complexity
            )
            feature.frontend_completion_pct = min(
                1.0, feature.frontend_completion_pct + fe_increment
            )

    if level == EffortLevel.ACCELERATED and not is_qa:
        feature.quality_score = max(0.0, feature.quality_score - ACCELERATED_QUALITY_PENALTY)

    budget.record_spend(
        round_number=round_number,
        amount=effort_units,
        category=f"{level.value}_effort",
    )

    update_feature_status(feature=feature)

    be_pct = feature.backend_completion_pct
    fe_pct = feature.frontend_completion_pct
    return (
        f"{feature.name}: {level.value} priority set for this week. "
        f"Backend {be_pct:.0%}, Frontend {fe_pct:.0%}."
    )


def _progress_increment(effort_units: float, complexity: int) -> float:
    """Convert effort units into a completion percentage increment."""
    if complexity <= 0:
        return 0.0
    return min(1.0, (effort_units * EFFORT_TO_PROGRESS_BASE) / complexity)


def update_feature_status(feature: Feature) -> None:
    """Recompute a feature's lifecycle status from its completion percentages."""
    if feature.backend_completion_pct <= 0.0 and feature.frontend_completion_pct <= 0.0:
        feature.status = FeatureStatus.NOT_STARTED
    elif feature.backend_completion_pct >= 1.0 and feature.frontend_completion_pct >= 1.0:
        if feature.qa.passed:
            feature.status = FeatureStatus.SHIPPED
        elif feature.qa.tested:
            if feature.qa.bugs_found > feature.qa.bugs_fixed:
                feature.status = FeatureStatus.QA_FAILED
            else:
                feature.status = FeatureStatus.QA_PASSED
        else:
            feature.status = FeatureStatus.INTEGRATION_READY
    elif feature.backend_completion_pct >= 1.0:
        feature.status = FeatureStatus.BACKEND_COMPLETE
    elif feature.frontend_completion_pct >= 1.0:
        feature.status = FeatureStatus.FRONTEND_COMPLETE
    else:
        feature.status = FeatureStatus.IN_PROGRESS


def run_qa_on_feature(feature: Feature) -> str:
    """Simulate QA testing on a feature.

    Bug probability scales with complexity and inversely with quality.
    """
    if feature.backend_completion_pct < 1.0 or feature.frontend_completion_pct < 1.0:
        return f"Cannot QA {feature.name}: not fully implemented yet."

    avg_complexity = (feature.backend_complexity + feature.frontend_complexity) / 2.0
    bug_probability = BUG_BASE_PROBABILITY + (1.0 - feature.quality_score) * 0.3
    num_bugs = sum(1 for _ in range(int(avg_complexity)) if random.random() < bug_probability)

    feature.qa.tested = True
    feature.qa.bugs_found += num_bugs
    if num_bugs == 0:
        feature.qa.passed = True
        feature.status = FeatureStatus.QA_PASSED
        return f"QA passed for {feature.name}. No bugs found."
    feature.status = FeatureStatus.QA_FAILED
    return f"QA found {num_bugs} bug(s) in {feature.name}. Needs fixing."


def fix_bugs_on_feature(
    feature: Feature,
    effort_units: float,
    budget: BudgetTracker,
    round_number: int,
) -> str:
    """Apply effort to fix bugs found during QA."""
    if feature.qa.bugs_found <= feature.qa.bugs_fixed:
        return f"No outstanding bugs to fix on {feature.name}."

    remaining_bugs = feature.qa.bugs_found - feature.qa.bugs_fixed
    fixes = min(remaining_bugs, int(effort_units))
    feature.qa.bugs_fixed += fixes

    budget.record_spend(
        round_number=round_number,
        amount=effort_units,
        category="bug_fixing",
    )

    if feature.qa.bugs_fixed >= feature.qa.bugs_found:
        feature.qa.passed = True
        feature.status = FeatureStatus.QA_PASSED
        return f"Fixed {fixes} bug(s) on {feature.name}. All bugs resolved — QA passed."
    still_remaining = feature.qa.bugs_found - feature.qa.bugs_fixed
    return f"Fixed {fixes} bug(s) on {feature.name}. {still_remaining} bug(s) remaining."


EXTERNAL_EVENTS: dict[str, dict[str, Any]] = {
    "competitor_announcement": {
        "description": "A competitor just announced a similar product launching in Week 10.",
        "effect": "Increased urgency — management wants the launch accelerated.",
        "visible_to": ["pm", "data_analyst"],
    },
    "api_breaking_change": {
        "description": (
            "A critical third-party API used by the Data Sync Engine connectors "
            "has announced a breaking change effective next week."
        ),
        "effect": (
            "Backend complexity on Data Sync Engine (F2) and "
            "Predictive Analytics Pipeline (F3) increases by +3."
        ),
        "visible_to": ["backend_engineer"],
    },
    "executive_review": {
        "description": (
            "Executive review scheduled. The PM must compile and publish "
            "the Launch Readiness Report this week."
        ),
        "effect": "PM must update the Launch Readiness Report shared document.",
        "visible_to": ["pm"],
    },
    "regression_discovered": {
        "description": (
            "Major bug discovered: a feature previously marked as QA-passed "
            "now fails integration tests."
        ),
        "effect": "One QA-passed feature reverts to QA_FAILED with 2 new bugs.",
        "visible_to": ["qa_lead"],
    },
}


def get_external_event_for_round(
    round_number: int,
    num_rounds: int,
    intensity: str,
) -> str | None:
    """Return the external event key for a given round, or None."""
    event_schedule: dict[int, str] = {}
    if num_rounds >= 8:
        event_schedule[3] = "competitor_announcement"
        event_schedule[5] = "api_breaking_change"
        event_schedule[8] = "executive_review"
        if intensity in ("medium", "high"):
            event_schedule[10] = "regression_discovered"
    elif num_rounds >= 5:
        event_schedule[2] = "competitor_announcement"
        event_schedule[4] = "api_breaking_change"
        if intensity in ("medium", "high"):
            event_schedule[5] = "executive_review"

    return event_schedule.get(round_number)


def apply_external_event(
    event_key: str,
    features: list[Feature],
) -> list[str]:
    """Apply the effects of an external event to the feature set."""
    changes: list[str] = []

    if event_key == "api_breaking_change":
        targets = [f for f in features if f.feature_id in ("feature_2", "feature_3")]
        if not targets:
            targets = features[:2]
        for f in targets:
            old_be = f.backend_complexity
            f.backend_complexity = min(10, f.backend_complexity + 3)
            update_feature_status(feature=f)
            changes.append(
                f"{f.name} backend complexity: {old_be} -> {f.backend_complexity} (API rework)"
            )

    elif event_key == "regression_discovered":
        qa_passed = [f for f in features if f.status == FeatureStatus.QA_PASSED]
        if qa_passed:
            target = random.choice(qa_passed)
            target.qa.bugs_found += 2
            target.qa.passed = False
            target.status = FeatureStatus.QA_FAILED
            changes.append(f"{target.name} regressed: 2 new bugs, QA status reverted.")

    return changes
