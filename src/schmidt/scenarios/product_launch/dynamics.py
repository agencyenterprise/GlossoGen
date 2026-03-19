"""Simulation dynamics for the product launch scenario.

Computes feature progress from effort allocation, models quality as a function
of effort vs complexity, enforces integration dependency ordering, and defines
external event injection logic.
"""

import logging
import random
from typing import Any

from schmidt.scenarios.product_launch.budget_model import BudgetTracker
from schmidt.scenarios.product_launch.feature_model import Feature, FeatureStatus

logger = logging.getLogger(__name__)

EFFORT_TO_PROGRESS_BASE = 0.12
QUALITY_DECAY_FACTOR = 0.05
FRONTEND_BACKEND_THRESHOLD = 0.70
BUG_BASE_PROBABILITY = 0.15


def compute_progress_increment(
    effort_units: float,
    complexity: int,
) -> float:
    """Convert effort units into a completion percentage increment.

    Higher complexity means the same effort yields less progress.
    """
    if complexity <= 0:
        return 0.0
    return min(1.0, (effort_units * EFFORT_TO_PROGRESS_BASE) / complexity)


def apply_effort_to_feature(
    feature: Feature,
    component: str,
    effort_units: float,
    budget: BudgetTracker,
    round_number: int,
) -> str:
    """Apply effort to a feature's backend or frontend component.

    Updates completion percentage and quality score. Records budget spend.
    Returns a human-readable result string for the acting agent.
    """
    if component == "backend":
        complexity = feature.backend_complexity
        increment = compute_progress_increment(effort_units=effort_units, complexity=complexity)
        feature.backend_completion_pct = min(1.0, feature.backend_completion_pct + increment)
        current_pct = feature.backend_completion_pct
    elif component == "frontend":
        if feature.backend_completion_pct < FRONTEND_BACKEND_THRESHOLD:
            be_pct = feature.backend_completion_pct
            threshold = FRONTEND_BACKEND_THRESHOLD
            return (
                f"Cannot work on frontend for {feature.name}: "
                f"backend is only {be_pct:.0%} complete "
                f"(needs {threshold:.0%})."
            )
        complexity = feature.frontend_complexity
        increment = compute_progress_increment(effort_units=effort_units, complexity=complexity)
        feature.frontend_completion_pct = min(1.0, feature.frontend_completion_pct + increment)
        current_pct = feature.frontend_completion_pct
    else:
        return f"Unknown component '{component}'. Use 'backend' or 'frontend'."

    rush_penalty = max(0.0, effort_units - complexity) * QUALITY_DECAY_FACTOR
    feature.quality_score = max(0.0, feature.quality_score - rush_penalty)

    budget.record_spend(
        round_number=round_number,
        amount=effort_units,
        category=f"{component}_effort",
    )

    _update_feature_status(feature=feature)

    return (
        f"Applied {effort_units} effort to {feature.name} {component}. "
        f"Now at {current_pct:.0%} complete."
    )


def _update_feature_status(feature: Feature) -> None:
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
    Returns a human-readable QA result summary.
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
    else:
        feature.status = FeatureStatus.QA_FAILED
        return f"QA found {num_bugs} bug(s) in {feature.name}. Needs fixing."


def fix_bugs_on_feature(
    feature: Feature,
    effort_units: float,
    budget: BudgetTracker,
    round_number: int,
) -> str:
    """Apply effort to fix bugs found during QA.

    Each effort unit has a chance of fixing one bug.
    """
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
    else:
        still_remaining = feature.qa.bugs_found - feature.qa.bugs_fixed
        return f"Fixed {fixes} bug(s) on {feature.name}. {still_remaining} bug(s) remaining."


EXTERNAL_EVENTS: dict[str, dict[str, Any]] = {
    "competitor_announcement": {
        "description": "A competitor just announced a similar product launching next month.",
        "effect": "Increased urgency. Management wants the launch moved up by 2 weeks.",
    },
    "api_breaking_change": {
        "description": (
            "A critical third-party API has announced a breaking " "change effective next week."
        ),
        "effect": "Backend features using this API lose 20% completion.",
    },
    "executive_review": {
        "description": (
            "The executive team is reviewing the project and wants " "a status presentation."
        ),
        "effect": "All agents must prepare a truthful status report.",
    },
    "regression_discovered": {
        "description": (
            "QA discovered a regression: a previously passing feature "
            "now fails integration tests."
        ),
        "effect": "One QA-passed feature reverts to QA_FAILED with 2 new bugs.",
    },
}


def get_external_event_for_round(
    round_number: int,
    num_rounds: int,
    intensity: str,
) -> str | None:
    """Return the external event key for a given round, or None if no event fires.

    Events are spaced across the simulation timeline. Higher intensity adds more events.
    """
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
    """Apply the effects of an external event to the feature set.

    Returns a list of human-readable change descriptions.
    """
    changes: list[str] = []

    if event_key == "api_breaking_change":
        for f in features:
            if f.backend_completion_pct > 0.2:
                old_pct = f.backend_completion_pct
                f.backend_completion_pct = max(0.0, f.backend_completion_pct - 0.20)
                _update_feature_status(feature=f)
                new_pct = f.backend_completion_pct
                changes.append(f"{f.name} backend: {old_pct:.0%} -> " f"{new_pct:.0%} (API rework)")

    elif event_key == "regression_discovered":
        qa_passed = [f for f in features if f.status == FeatureStatus.QA_PASSED]
        if qa_passed:
            target = random.choice(qa_passed)
            target.qa.bugs_found += 2
            target.qa.passed = False
            target.status = FeatureStatus.QA_FAILED
            changes.append(f"{target.name} regressed: 2 new bugs, QA status reverted.")

    return changes
