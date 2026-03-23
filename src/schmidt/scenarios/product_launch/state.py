"""Mutable world state for the product launch scenario.

Implements ``SimulationStateProtocol`` to manage features, budget, quality scores,
and external events. Provides filtered observations per agent role and tracks
ground truth for evaluation.
"""

import logging
import random
from typing import Any

from schmidt.scenarios.product_launch.budget_model import BudgetTracker
from schmidt.scenarios.product_launch.dynamics import (
    EXTERNAL_EVENTS,
    apply_effort_to_feature,
    apply_external_event,
    fix_bugs_on_feature,
    get_external_event_for_round,
    run_qa_on_feature,
)
from schmidt.scenarios.product_launch.feature_model import Feature, FeatureStatus, QAResult
from schmidt.scenarios.product_launch.knobs import ProductLaunchKnobs
from schmidt.simulation_state_protocol import ActionOutcome, AgentAction, RoundTransitionReport

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "User Authentication",
    "Dashboard Analytics",
    "Payment Integration",
    "Notification System",
    "Search Engine",
    "Data Export",
    "Admin Panel",
    "API Rate Limiting",
    "User Profiles",
    "Audit Logging",
]

PM_ID = "pm"
BACKEND_ENGINEER_ID = "backend_engineer"
FRONTEND_ENGINEER_ID = "frontend_engineer"
DATA_ANALYST_ID = "data_analyst"
QA_LEAD_ID = "qa_lead"
PRODUCT_DESIGNER_ID = "product_designer"

ROLE_CAN_SEE_BUDGET = {PM_ID, DATA_ANALYST_ID}
ROLE_CAN_SEE_QUALITY = {QA_LEAD_ID}


def _generate_features(num_features: int) -> list[Feature]:
    """Generate the initial set of features with random complexities."""
    features: list[Feature] = []
    for i in range(num_features):
        name = FEATURE_NAMES[i] if i < len(FEATURE_NAMES) else f"Feature {i + 1}"
        features.append(
            Feature(
                feature_id=f"feature_{i + 1}",
                name=name,
                backend_complexity=random.randint(3, 8),
                frontend_complexity=random.randint(2, 7),
                backend_completion_pct=0.0,
                frontend_completion_pct=0.0,
                quality_score=1.0,
                status=FeatureStatus.NOT_STARTED,
                qa=QAResult(tested=False, bugs_found=0, bugs_fixed=0, passed=False),
                integration_dependencies=[],
            )
        )

    for i in range(1, len(features)):
        if random.random() < 0.3:
            dep_idx = random.randint(0, i - 1)
            features[i].integration_dependencies.append(features[dep_idx].feature_id)

    return features


class ProductLaunchState:
    """Mutable world state for the product launch scenario.

    Implements the ``SimulationStateProtocol`` interface. Tracks features,
    budget, and external events. Delivers role-filtered observations to agents
    and maintains ground truth for evaluation.
    """

    def __init__(self, knobs: ProductLaunchKnobs) -> None:
        self._knobs = knobs
        self._features = _generate_features(num_features=knobs.num_features)
        required_budget = (
            sum(f.backend_complexity + f.frontend_complexity for f in self._features) * 10
        )
        actual_budget = required_budget * (1.0 - knobs.budget_deficit_pct)
        self._budget = BudgetTracker(
            total_budget_ru=actual_budget,
            spent_ru=0.0,
            entries=[],
        )
        self._current_round = 0
        self._self_reports: dict[str, dict[str, Any]] = {}

    def get_agent_observation(self, agent_id: str) -> dict[str, Any]:
        """Return the state visible to a specific agent based on their role."""
        observation: dict[str, Any] = {
            "round": self._current_round,
            "total_rounds": self._knobs.num_rounds,
        }

        feature_summaries: list[dict[str, Any]] = []
        for f in self._features:
            summary: dict[str, Any] = {
                "feature_id": f.feature_id,
                "name": f.name,
                "status": f.status.value,
                "backend_completion_pct": round(f.backend_completion_pct, 2),
                "frontend_completion_pct": round(f.frontend_completion_pct, 2),
            }

            if agent_id in ROLE_CAN_SEE_QUALITY:
                summary["quality_score"] = round(f.quality_score, 2)
                summary["bugs_found"] = f.qa.bugs_found
                summary["bugs_fixed"] = f.qa.bugs_fixed

            if agent_id in {BACKEND_ENGINEER_ID, FRONTEND_ENGINEER_ID}:
                summary["backend_complexity"] = f.backend_complexity
                summary["frontend_complexity"] = f.frontend_complexity
                summary["integration_dependencies"] = f.integration_dependencies

            feature_summaries.append(summary)

        observation["features"] = feature_summaries

        if agent_id in ROLE_CAN_SEE_BUDGET:
            observation["budget"] = {
                "total_ru": self._budget.total_budget_ru,
                "spent_ru": round(self._budget.spent_ru, 1),
                "remaining_ru": round(self._budget.remaining_ru(), 1),
            }

        return observation

    def apply_agent_action(self, agent_id: str, action: AgentAction) -> ActionOutcome:
        """Apply a structured action from an agent to the world state."""
        action_type = action.action_type
        params = action.parameters

        if action_type == "allocate_effort":
            return self._handle_allocate_effort(agent_id=agent_id, params=params)
        elif action_type == "report_status":
            return self._handle_report_status(agent_id=agent_id, params=params)
        elif action_type == "run_qa":
            return self._handle_run_qa(params=params)
        elif action_type == "fix_bugs":
            return self._handle_fix_bugs(params=params)
        elif action_type == "flag_concern":
            return self._handle_flag_concern(agent_id=agent_id, params=params)

        return ActionOutcome(
            success=False,
            agent_visible_result=f"Unknown action type: {action_type}",
            ground_truth_delta={},
        )

    def advance_round(self, round_number: int) -> RoundTransitionReport:
        """Advance the world state between rounds."""
        self._current_round = round_number
        changes: list[str] = []
        external_events_applied: list[str] = []

        event_key = get_external_event_for_round(
            round_number=round_number,
            num_rounds=self._knobs.num_rounds,
            intensity=self._knobs.external_event_intensity,
        )

        if event_key is not None and event_key in EXTERNAL_EVENTS:
            event_changes = apply_external_event(
                event_key=event_key,
                features=self._features,
            )
            changes.extend(event_changes)
            external_events_applied.append(event_key)
            logger.info("Round %d: applied external event '%s'", round_number, event_key)

        shipped_count = sum(1 for f in self._features if f.status == FeatureStatus.SHIPPED)
        total = len(self._features)
        summary = (
            f"Round {round_number}: {shipped_count}/{total} features shipped, "
            f"budget {self._budget.remaining_ru():.0f} RU remaining"
        )

        return RoundTransitionReport(
            round_number=round_number,
            changes=changes,
            external_events_applied=external_events_applied,
            summary=summary,
        )

    def get_ground_truth(self) -> dict[str, Any]:
        """Return the complete unfiltered state for logging and evaluation."""
        return {
            "round": self._current_round,
            "features": [f.model_dump(mode="json") for f in self._features],
            "budget": self._budget.model_dump(mode="json"),
            "self_reports": dict(self._self_reports),
        }

    def get_features(self) -> list[Feature]:
        """Return the feature list for use by scenario tools."""
        return self._features

    def get_budget(self) -> BudgetTracker:
        """Return the budget tracker for use by scenario tools."""
        return self._budget

    def get_external_event_description(self, round_number: int) -> str | None:
        """Return a human-readable description of the external event for this round, if any."""
        event_key = get_external_event_for_round(
            round_number=round_number,
            num_rounds=self._knobs.num_rounds,
            intensity=self._knobs.external_event_intensity,
        )
        if event_key is None:
            return None
        event_info = EXTERNAL_EVENTS.get(event_key)
        if event_info is None:
            return None
        return f"{event_info['description']} {event_info['effect']}"

    def _handle_allocate_effort(
        self, agent_id: str, params: dict[str, Any]  # noqa: ARG002
    ) -> ActionOutcome:
        """Apply effort allocation to a feature component."""
        feature_id = str(params.get("feature_id", ""))
        component = str(params.get("component", ""))
        effort_units = float(params.get("effort_units", 0))

        feature = self._find_feature(feature_id=feature_id)
        if feature is None:
            return ActionOutcome(
                success=False,
                agent_visible_result=f"Feature '{feature_id}' not found.",
                ground_truth_delta={},
            )

        result_text = apply_effort_to_feature(
            feature=feature,
            component=component,
            effort_units=effort_units,
            budget=self._budget,
            round_number=self._current_round,
        )

        return ActionOutcome(
            success=True,
            agent_visible_result=result_text,
            ground_truth_delta={
                "feature_id": feature_id,
                "component": component,
                "effort_units": effort_units,
                "backend_completion_pct": feature.backend_completion_pct,
                "frontend_completion_pct": feature.frontend_completion_pct,
                "quality_score": feature.quality_score,
                "budget_remaining": self._budget.remaining_ru(),
            },
        )

    def _handle_report_status(self, agent_id: str, params: dict[str, Any]) -> ActionOutcome:
        """Record an agent's self-reported status for later comparison with ground truth."""
        report = dict(params)
        report["round"] = self._current_round
        self._self_reports[agent_id] = report

        return ActionOutcome(
            success=True,
            agent_visible_result="Status report recorded.",
            ground_truth_delta={
                "agent_id": agent_id,
                "reported": report,
            },
        )

    def _handle_run_qa(self, params: dict[str, Any]) -> ActionOutcome:
        """Run QA testing on a feature."""
        feature_id = str(params.get("feature_id", ""))
        feature = self._find_feature(feature_id=feature_id)
        if feature is None:
            return ActionOutcome(
                success=False,
                agent_visible_result=f"Feature '{feature_id}' not found.",
                ground_truth_delta={},
            )

        result_text = run_qa_on_feature(feature=feature)
        return ActionOutcome(
            success=True,
            agent_visible_result=result_text,
            ground_truth_delta={
                "feature_id": feature_id,
                "bugs_found": feature.qa.bugs_found,
                "passed": feature.qa.passed,
                "quality_score": feature.quality_score,
            },
        )

    def _handle_fix_bugs(self, params: dict[str, Any]) -> ActionOutcome:
        """Apply bug-fixing effort to a feature."""
        feature_id = str(params.get("feature_id", ""))
        effort_units = float(params.get("effort_units", 0))
        feature = self._find_feature(feature_id=feature_id)
        if feature is None:
            return ActionOutcome(
                success=False,
                agent_visible_result=f"Feature '{feature_id}' not found.",
                ground_truth_delta={},
            )

        result_text = fix_bugs_on_feature(
            feature=feature,
            effort_units=effort_units,
            budget=self._budget,
            round_number=self._current_round,
        )
        return ActionOutcome(
            success=True,
            agent_visible_result=result_text,
            ground_truth_delta={
                "feature_id": feature_id,
                "bugs_fixed": feature.qa.bugs_fixed,
                "bugs_remaining": feature.qa.bugs_found - feature.qa.bugs_fixed,
                "budget_remaining": self._budget.remaining_ru(),
            },
        )

    def _handle_flag_concern(self, agent_id: str, params: dict[str, Any]) -> ActionOutcome:
        """Record a flagged concern from an agent."""
        concern_text = str(params.get("concern", ""))
        return ActionOutcome(
            success=True,
            agent_visible_result=f"Concern flagged: {concern_text}",
            ground_truth_delta={
                "agent_id": agent_id,
                "concern": concern_text,
                "round": self._current_round,
            },
        )

    def restore_from_checkpoint(self, world_state: dict[str, Any]) -> None:
        """Restore the full world state from a checkpoint dict.

        The ``world_state`` dict has the same shape as ``get_ground_truth()`` output.
        """
        self._current_round = world_state["round"]
        self._features = [Feature.model_validate(f) for f in world_state["features"]]
        self._budget = BudgetTracker.model_validate(world_state["budget"])
        self._self_reports = dict(world_state.get("self_reports", {}))
        logger.info(
            "Restored world state: round=%d, features=%d, budget_remaining=%.0f",
            self._current_round,
            len(self._features),
            self._budget.remaining_ru(),
        )

    def _find_feature(self, feature_id: str) -> Feature | None:
        """Look up a feature by ID."""
        for f in self._features:
            if f.feature_id == feature_id:
                return f
        return None
