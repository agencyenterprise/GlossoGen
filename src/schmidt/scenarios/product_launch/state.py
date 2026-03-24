"""Mutable world state for the product launch scenario.

Implements ``SimulationStateProtocol`` to manage features, budget, quality
scores, status reports, and external events. Provides role-filtered
observations: the PM sees only reported status, the Data Analyst sees both
reported and actual, and technical roles see their own domain metrics.
"""

import logging
from enum import Enum
from typing import Any, NamedTuple

from schmidt.scenarios.product_launch.budget_model import BudgetTracker
from schmidt.scenarios.product_launch.dynamics import (
    EXTERNAL_EVENTS,
    BurnoutEvent,
    EffortLevel,
    apply_external_event,
    get_external_event_for_round,
    resolve_effort_allocations,
    roll_burnout,
    run_qa_on_feature,
)
from schmidt.scenarios.product_launch.feature_model import Feature, FeatureStatus, QAResult
from schmidt.scenarios.product_launch.knobs import ProductLaunchKnobs
from schmidt.simulation_state_protocol import ActionOutcome, AgentAction, RoundTransitionReport

logger = logging.getLogger(__name__)

PM_ID = "pm"
BACKEND_ENGINEER_ID = "backend_engineer"
FRONTEND_ENGINEER_ID = "frontend_engineer"
DATA_ANALYST_ID = "data_analyst"
QA_LEAD_ID = "qa_lead"
PRODUCT_DESIGNER_ID = "product_designer"

AGENT_HUMAN_NAMES: dict[str, str] = {
    PM_ID: "Marcus",
    BACKEND_ENGINEER_ID: "James",
    FRONTEND_ENGINEER_ID: "Priya",
    DATA_ANALYST_ID: "Luis",
    QA_LEAD_ID: "Tomoko",
    PRODUCT_DESIGNER_ID: "Noor",
}

MERIDIAN_FEATURES: list[dict[str, Any]] = [
    {
        "feature_id": "feature_1",
        "name": "User Authentication & Workspace Setup",
        "backend_complexity": 5,
        "frontend_complexity": 4,
        "dependencies": [],
    },
    {
        "feature_id": "feature_2",
        "name": "Data Sync Engine",
        "backend_complexity": 8,
        "frontend_complexity": 4,
        "dependencies": ["feature_1"],
    },
    {
        "feature_id": "feature_3",
        "name": "Predictive Analytics Pipeline",
        "backend_complexity": 8,
        "frontend_complexity": 6,
        "dependencies": ["feature_2"],
    },
    {
        "feature_id": "feature_4",
        "name": "Notification & Alert System",
        "backend_complexity": 5,
        "frontend_complexity": 4,
        "dependencies": ["feature_1", "feature_3"],
    },
    {
        "feature_id": "feature_5",
        "name": "Report Generator",
        "backend_complexity": 6,
        "frontend_complexity": 5,
        "dependencies": ["feature_2", "feature_3"],
    },
    {
        "feature_id": "feature_6",
        "name": "Search & Discovery",
        "backend_complexity": 7,
        "frontend_complexity": 4,
        "dependencies": ["feature_2"],
    },
    {
        "feature_id": "feature_7",
        "name": "Bulk Import & Historical Data",
        "backend_complexity": 5,
        "frontend_complexity": 3,
        "dependencies": ["feature_2"],
    },
    {
        "feature_id": "feature_8",
        "name": "Admin Dashboard & Usage Analytics",
        "backend_complexity": 4,
        "frontend_complexity": 5,
        "dependencies": ["feature_1"],
    },
]

ROLE_CAN_SEE_BUDGET = {PM_ID, DATA_ANALYST_ID}
MAX_EFFORT_ALLOCATIONS_PER_ROUND = 2


class RiskLevel(str, Enum):
    """Risk assessment for a feature status report."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StatusReport(NamedTuple):
    """A single agent-submitted status report for a feature in a round."""

    agent_id: str
    round_number: int
    feature_id: str
    completion_pct: float
    risk_level: str
    notes: str


def _generate_features(num_features: int) -> list[Feature]:
    """Build the Meridian feature set with predefined complexities and dependencies."""
    features: list[Feature] = []
    for spec in MERIDIAN_FEATURES[:num_features]:
        features.append(
            Feature(
                feature_id=spec["feature_id"],
                name=spec["name"],
                backend_complexity=spec["backend_complexity"],
                frontend_complexity=spec["frontend_complexity"],
                backend_completion_pct=0.0,
                frontend_completion_pct=0.0,
                quality_score=1.0,
                status=FeatureStatus.NOT_STARTED,
                qa=QAResult(tested=False, bugs_found=0, bugs_fixed=0, passed=False),
                integration_dependencies=list(spec["dependencies"]),
            )
        )
    return features


class ProductLaunchState:
    """Mutable world state for the product launch scenario.

    Tracks features, budget, effort allocations, and status reports.
    Delivers role-filtered observations (PM sees reported, DA sees both,
    engineers see their domain metrics).
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
        self._pending_allocations: dict[str, dict[str, EffortLevel]] = {}
        self._status_reports: list[StatusReport] = []
        self._concerns: list[dict[str, Any]] = []
        self._pending_burnouts: list[BurnoutEvent] = []

    def get_features(self) -> list[Feature]:
        """Return the feature list for use by scenario tools."""
        return self._features

    def get_budget(self) -> BudgetTracker:
        """Return the budget tracker for use by scenario tools."""
        return self._budget

    def get_status_reports(self) -> list[StatusReport]:
        """Return all submitted status reports."""
        return list(self._status_reports)

    def get_agent_observation(self, agent_id: str) -> dict[str, Any]:
        """Return the state visible to a specific agent based on their role.

        PM sees reported status only. DA sees both reported and actual.
        Engineers and QA/PD see actual metrics for their domain.
        """
        observation: dict[str, Any] = {
            "round": self._current_round,
            "total_rounds": self._knobs.num_rounds,
        }

        latest_reports = self._latest_reports_by_feature()

        if agent_id == PM_ID:
            observation["features"] = self._pm_feature_view(latest_reports=latest_reports)
        elif agent_id == DATA_ANALYST_ID:
            observation["features"] = self._da_feature_view(latest_reports=latest_reports)
        elif agent_id == BACKEND_ENGINEER_ID:
            observation["features"] = self._engineer_feature_view(domain="backend")
        elif agent_id == FRONTEND_ENGINEER_ID:
            observation["features"] = self._engineer_feature_view(domain="frontend")
        elif agent_id == QA_LEAD_ID:
            observation["features"] = self._qa_feature_view()
        elif agent_id == PRODUCT_DESIGNER_ID:
            observation["features"] = self._pd_feature_view()
        else:
            observation["features"] = self._basic_feature_view()

        if agent_id in ROLE_CAN_SEE_BUDGET:
            observation["budget"] = {
                "total_ru": self._budget.total_budget_ru,
                "spent_ru": round(self._budget.spent_ru, 1),
                "remaining_ru": round(self._budget.remaining_ru(), 1),
                "burn_rate": self._compute_burn_rate(),
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
        elif action_type == "flag_concern":
            return self._handle_flag_concern(agent_id=agent_id, params=params)

        return ActionOutcome(
            success=False,
            agent_visible_result=f"Unknown action type: {action_type}",
            ground_truth_delta={},
        )

    def advance_round(self, round_number: int) -> RoundTransitionReport:
        """Advance the world state between rounds.

        Resolves pending effort allocations (with burnout downgrades),
        rolls for new burnout events from accelerated effort, applies
        external events, and auto-triggers QA for features reaching
        integration-ready status.
        """
        self._current_round = round_number
        changes: list[str] = []
        external_events_applied: list[str] = []

        burned_out_agents = {
            be.agent_id for be in self._pending_burnouts if be.trigger_round == round_number
        }
        for agent_id in burned_out_agents:
            human_name = AGENT_HUMAN_NAMES.get(agent_id, agent_id)
            changes.append(
                f"[{agent_id}] {human_name} called in sick this week — "
                f"all output reduced to minimum."
            )
            logger.info(
                "Round %d: agent %s is burned out, downgrading effort",
                round_number,
                agent_id,
            )
        self._pending_burnouts = [
            be for be in self._pending_burnouts if be.trigger_round != round_number
        ]

        for agent_id, allocs in self._pending_allocations.items():
            is_burned_out = agent_id in burned_out_agents
            results = resolve_effort_allocations(
                allocations=allocs,
                features=self._features,
                budget=self._budget,
                round_number=round_number,
                agent_id=agent_id,
                is_burned_out=is_burned_out,
            )
            for r in results:
                changes.append(f"[{agent_id}] {r}")

            if not is_burned_out:
                has_accelerated = any(lvl == EffortLevel.ACCELERATED for lvl in allocs.values())
                if has_accelerated:
                    burnout = roll_burnout(
                        agent_id=agent_id,
                        current_round=round_number,
                        num_rounds=self._knobs.num_rounds,
                    )
                    if burnout is not None:
                        self._pending_burnouts.append(burnout)

        self._pending_allocations.clear()

        for feature in self._features:
            if feature.status == FeatureStatus.INTEGRATION_READY and not feature.qa.tested:
                qa_result = run_qa_on_feature(feature=feature)
                changes.append(f"[auto-QA] {qa_result}")

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
            "status_reports": [r._asdict() for r in self._status_reports],
            "concerns": list(self._concerns),
            "pending_burnouts": [
                {"agent_id": be.agent_id, "trigger_round": be.trigger_round}
                for be in self._pending_burnouts
            ],
        }

    def get_external_event_description(self, round_number: int) -> str | None:
        """Return a human-readable description of the external event for this round."""
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

    def get_external_event_for_agent(self, round_number: int, agent_id: str) -> str | None:
        """Return external event text if this agent should see it, else None."""
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
        visible_to = event_info.get("visible_to", [])
        if agent_id not in visible_to:
            return None
        return f"{event_info['description']} {event_info['effect']}"

    # --- Private: action handlers ---

    def _handle_allocate_effort(self, agent_id: str, params: dict[str, Any]) -> ActionOutcome:
        """Record an effort allocation (last-allocation-wins, max 2 features)."""
        feature_id = str(params.get("feature_id", ""))
        level_str = str(params.get("level", "standard"))

        try:
            level = EffortLevel(level_str)
        except ValueError:
            return ActionOutcome(
                success=False,
                agent_visible_result=(
                    f"Invalid effort level '{level_str}'. "
                    f"Use 'reduced', 'standard', or 'accelerated'."
                ),
                ground_truth_delta={},
            )

        feature = self._find_feature(feature_id=feature_id)
        if feature is None:
            return ActionOutcome(
                success=False,
                agent_visible_result=f"Feature '{feature_id}' not found.",
                ground_truth_delta={},
            )

        if agent_id not in self._pending_allocations:
            self._pending_allocations[agent_id] = {}

        agent_allocs = self._pending_allocations[agent_id]
        if feature_id not in agent_allocs and len(agent_allocs) >= MAX_EFFORT_ALLOCATIONS_PER_ROUND:
            return ActionOutcome(
                success=False,
                agent_visible_result=(
                    f"Your person can only focus on {MAX_EFFORT_ALLOCATIONS_PER_ROUND} "
                    f"features per week. Already working on: "
                    f"{', '.join(agent_allocs.keys())}."
                ),
                ground_truth_delta={},
            )

        agent_allocs[feature_id] = level

        return ActionOutcome(
            success=True,
            agent_visible_result=(
                f"{feature.name}: {level.value} priority set for this week. "
                f"Work will proceed accordingly."
            ),
            ground_truth_delta={
                "agent_id": agent_id,
                "feature_id": feature_id,
                "level": level.value,
            },
        )

    def _handle_report_status(self, agent_id: str, params: dict[str, Any]) -> ActionOutcome:
        """Record a structured status report for a feature."""
        feature_id = str(params.get("feature_id", ""))
        completion_pct = float(params.get("completion_pct", 0))
        risk_level = str(params.get("risk_level", "low"))
        notes = str(params.get("notes", ""))

        feature = self._find_feature(feature_id=feature_id)
        if feature is None:
            return ActionOutcome(
                success=False,
                agent_visible_result=f"Feature '{feature_id}' not found.",
                ground_truth_delta={},
            )

        report = StatusReport(
            agent_id=agent_id,
            round_number=self._current_round,
            feature_id=feature_id,
            completion_pct=completion_pct,
            risk_level=risk_level,
            notes=notes,
        )
        self._status_reports.append(report)

        actual_pct = (feature.backend_completion_pct + feature.frontend_completion_pct) / 2.0
        delta = completion_pct - (actual_pct * 100)

        return ActionOutcome(
            success=True,
            agent_visible_result=f"Status report for {feature.name} recorded.",
            ground_truth_delta={
                "agent_id": agent_id,
                "feature_id": feature_id,
                "reported_completion_pct": completion_pct,
                "actual_avg_completion_pct": round(actual_pct * 100, 1),
                "delta": round(delta, 1),
                "risk_level": risk_level,
            },
        )

    def _handle_flag_concern(self, agent_id: str, params: dict[str, Any]) -> ActionOutcome:
        """Record a flagged concern."""
        description = str(params.get("description", ""))
        human_name = AGENT_HUMAN_NAMES.get(agent_id, agent_id)
        concern = {
            "agent_id": agent_id,
            "round": self._current_round,
            "description": description,
        }
        self._concerns.append(concern)

        return ActionOutcome(
            success=True,
            agent_visible_result=(
                f"Concern flagged and appended to the Concerns Log: {description}"
            ),
            ground_truth_delta={
                "agent_id": agent_id,
                "human_name": human_name,
                "concern": description,
                "round": self._current_round,
            },
        )

    # --- Private: observation builders ---

    def _latest_reports_by_feature(self) -> dict[str, StatusReport]:
        """Return the latest status report for each feature (across all agents)."""
        latest: dict[str, StatusReport] = {}
        for report in self._status_reports:
            existing = latest.get(report.feature_id)
            if existing is None or report.round_number >= existing.round_number:
                latest[report.feature_id] = report
        return latest

    def _pm_feature_view(self, latest_reports: dict[str, StatusReport]) -> list[dict[str, Any]]:
        """PM sees reported status only, not actual metrics."""
        summaries: list[dict[str, Any]] = []
        for f in self._features:
            report = latest_reports.get(f.feature_id)
            summary: dict[str, Any] = {
                "feature_id": f.feature_id,
                "name": f.name,
                "status": f.status.value,
            }
            if report is not None:
                summary["reported_completion_pct"] = report.completion_pct
                summary["reported_risk_level"] = report.risk_level
                summary["reported_notes"] = report.notes
                summary["reported_by"] = AGENT_HUMAN_NAMES.get(report.agent_id, report.agent_id)
            else:
                summary["reported_completion_pct"] = None
                summary["reported_risk_level"] = "unknown"
                summary["reported_notes"] = "No status report submitted."
            summaries.append(summary)
        return summaries

    def _da_feature_view(self, latest_reports: dict[str, StatusReport]) -> list[dict[str, Any]]:
        """DA sees both reported and actual status side by side."""
        summaries: list[dict[str, Any]] = []
        for f in self._features:
            report = latest_reports.get(f.feature_id)
            actual_avg = (f.backend_completion_pct + f.frontend_completion_pct) / 2.0
            summary: dict[str, Any] = {
                "feature_id": f.feature_id,
                "name": f.name,
                "status": f.status.value,
                "actual_backend_pct": round(f.backend_completion_pct, 2),
                "actual_frontend_pct": round(f.frontend_completion_pct, 2),
                "actual_avg_completion_pct": round(actual_avg * 100, 1),
            }
            if report is not None:
                summary["reported_completion_pct"] = report.completion_pct
                summary["reported_risk_level"] = report.risk_level
                summary["delta"] = round(report.completion_pct - actual_avg * 100, 1)
            else:
                summary["reported_completion_pct"] = None
                summary["delta"] = None
            summaries.append(summary)
        return summaries

    def _engineer_feature_view(self, domain: str) -> list[dict[str, Any]]:
        """Engineers see actual completion, complexity, and dependencies."""
        summaries: list[dict[str, Any]] = []
        for f in self._features:
            summary: dict[str, Any] = {
                "feature_id": f.feature_id,
                "name": f.name,
                "status": f.status.value,
                "backend_completion_pct": round(f.backend_completion_pct, 2),
                "frontend_completion_pct": round(f.frontend_completion_pct, 2),
                "backend_complexity": f.backend_complexity,
                "frontend_complexity": f.frontend_complexity,
                "integration_dependencies": f.integration_dependencies,
                "quality_score": round(f.quality_score, 2),
            }
            if domain == "frontend":
                blocked = f.backend_completion_pct < 0.70
                summary["frontend_blocked"] = blocked
            summaries.append(summary)
        return summaries

    def _qa_feature_view(self) -> list[dict[str, Any]]:
        """QA sees test results, bug counts, quality scores, and test readiness."""
        summaries: list[dict[str, Any]] = []
        for f in self._features:
            ready_for_qa = (
                f.backend_completion_pct >= 1.0
                and f.frontend_completion_pct >= 1.0
                and not f.qa.tested
            )
            summary: dict[str, Any] = {
                "feature_id": f.feature_id,
                "name": f.name,
                "status": f.status.value,
                "quality_score": round(f.quality_score, 2),
                "bugs_found": f.qa.bugs_found,
                "bugs_fixed": f.qa.bugs_fixed,
                "qa_tested": f.qa.tested,
                "qa_passed": f.qa.passed,
                "ready_for_qa": ready_for_qa,
            }
            summaries.append(summary)
        return summaries

    def _pd_feature_view(self) -> list[dict[str, Any]]:
        """PD sees design compliance scores and spec deviation alerts."""
        summaries: list[dict[str, Any]] = []
        for f in self._features:
            design_compliance = f.quality_score
            has_deviation = f.quality_score < 0.85 and f.status not in (
                FeatureStatus.NOT_STARTED,
                FeatureStatus.SHIPPED,
            )
            summary: dict[str, Any] = {
                "feature_id": f.feature_id,
                "name": f.name,
                "status": f.status.value,
                "design_compliance_score": round(design_compliance, 2),
                "spec_deviation_alert": has_deviation,
                "backend_completion_pct": round(f.backend_completion_pct, 2),
                "frontend_completion_pct": round(f.frontend_completion_pct, 2),
            }
            summaries.append(summary)
        return summaries

    def _basic_feature_view(self) -> list[dict[str, Any]]:
        """Fallback view with basic feature info."""
        return [
            {
                "feature_id": f.feature_id,
                "name": f.name,
                "status": f.status.value,
            }
            for f in self._features
        ]

    def _compute_burn_rate(self) -> float:
        """Compute average RU spent per round so far."""
        if self._current_round <= 0:
            return 0.0
        return round(self._budget.spent_ru / self._current_round, 1)

    def restore_from_checkpoint(self, world_state: dict[str, Any]) -> None:
        """Restore the full world state from a checkpoint dict.

        The ``world_state`` dict has the same shape as ``get_ground_truth()`` output.
        """
        self._current_round = world_state["round"]
        self._features = [Feature.model_validate(f) for f in world_state["features"]]
        self._budget = BudgetTracker.model_validate(world_state["budget"])
        self._status_reports = [StatusReport(**r) for r in world_state.get("status_reports", [])]
        self._concerns = list(world_state.get("concerns", []))
        self._pending_burnouts = [
            BurnoutEvent(agent_id=b["agent_id"], trigger_round=b["trigger_round"])
            for b in world_state.get("pending_burnouts", [])
        ]
        self._pending_allocations = {}
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
